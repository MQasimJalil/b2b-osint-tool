import os
import time
import random
import json
from typing import List, Set, Dict, Optional, Tuple

import yaml
import httpx
import tldextract
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium import webdriver as std_webdriver
from selenium.webdriver.chrome.service import Service as StdService
from selenium.webdriver.chrome.options import Options as StdOptions
from tqdm import tqdm
from threading import Thread, Lock
from queue import Queue, Empty

HEADERS_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.89 Safari/537.36",
]

BLACKLIST = [
    'google.', 'youtube.', 'facebook.', 'linkedin.', 'instagram.', 'pinterest.', 'webcache.', 'amazon.', 'ebay.',
    'exporthub.', 'etradeasia.', 'alibaba.', 'etsy.', 'walmart.', 'tiktok.', 'temu.', 'daraz.'
]

SHOP_PATH_HINTS = [
    "/cart", "/checkout", "/product", "/products", "/collections", "/shop",
]

PLATFORM_FPS = [
    "cdn.shopify.com", "Shopify", "x-shopify-stage",
    "woocommerce", "/wp-json/wc/", "wp-content/plugins/woocommerce",
    "cdn.bcapp", "bigcommerce",
]

CACHE_DIR = os.path.join("pipeline", "cache")
QUERY_CACHE = os.path.join(CACHE_DIR, "query_cache.jsonl")
SOFTVET_CACHE = os.path.join(CACHE_DIR, "softvet_cache.jsonl")
DISCOVERED_JSONL = os.path.join(CACHE_DIR, "discovered_domains.jsonl")

# Serialize undetected_chromedriver patching to avoid race creating the executable on Windows
UC_INIT_LOCK = Lock()


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_config() -> Dict:
    path = os.path.join("pipeline", "discover_config.yaml")
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _load_set_from_jsonl(path: str, key: str) -> Set[str]:
    s: Set[str] = set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    val = obj.get(key)
                    if isinstance(val, str):
                        s.add(val)
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return s


def _load_discovered_set() -> Set[str]:
    return _load_set_from_jsonl(DISCOVERED_JSONL, "domain")


def _load_completed_queries() -> Set[str]:
    # Compose key as f"{engine}::{query}" from QUERY_CACHE
    s: Set[str] = set()
    try:
        with open(QUERY_CACHE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                    eng = row.get("engine")
                    q = row.get("query")
                    if eng and q:
                        s.add(f"{eng}::{q}")
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return s


def _append_jsonl(path: str, obj: Dict):
    _ensure_cache_dir()
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _generate_queries(industry: str, regions: List[str], languages: List[str]) -> List[str]:
    cfg = _load_config()
    tcfg = cfg.get("templates", {})

    intents: List[str] = tcfg.get("intents", ["buy", "price", "shop", "supplier", "wholesale"])  # defaults
    negatives: List[str] = tcfg.get("negatives", [])
    platform_hints: List[str] = tcfg.get("platform_hints", [])
    niche_terms: List[str] = tcfg.get("niche_terms", [industry])
    geo_tlds: List[str] = tcfg.get("geo_tlds", [])

    limits = cfg.get("limits", {})
    max_queries = int(limits.get("max_queries", 400))
    per_family_cap = int(limits.get("per_family_cap", 50))

    # Families: basic intent, platform hint, brand+intent, niche+platform, geo_tld combinations
    families: List[List[str]] = []

    # 1) industry + intent (+ negatives)
    fam_basic = [f"{industry} {intent} {' '.join(negatives)}".strip() for intent in intents]
    families.append(fam_basic)

    # 2) industry + platform hints (+ negatives)
    fam_platform = [f"{industry} {ph} {' '.join(negatives)}".strip() for ph in platform_hints]
    families.append(fam_platform)

    # 3) niche term + platform hint (+ negatives)
    fam_niche_platform = [f"{n} {ph} {' '.join(negatives)}".strip() for n in niche_terms for ph in platform_hints]
    families.append(fam_niche_platform)

    # 4) niche term + intent + geo tld (+ negatives)
    fam_geo = [f"{n} {intent} site:{tld} {' '.join(negatives)}".strip() for n in niche_terms for intent in intents for tld in geo_tlds]
    families.append(fam_geo)

    # 5) region/location terms
    fam_region = [f"{industry} {intent} {reg} {' '.join(negatives)}".strip() for reg in regions for intent in intents]
    families.append(fam_region)

    # Assemble with per-family cap and stratified sampling
    rnd = random.Random(42)
    queries: List[str] = []
    for fam in families:
        rnd.shuffle(fam)
        queries.extend(fam[:per_family_cap])

    # Dedupe, normalize whitespace
    seen: Set[str] = set()
    uniq: List[str] = []
    for q in queries:
        qn = ' '.join(q.split())
        if qn and qn not in seen:
            uniq.append(qn)
            seen.add(qn)

    # Trim to max_queries
    if len(uniq) > max_queries:
        rnd.shuffle(uniq)
        uniq = uniq[:max_queries]
    return uniq


def _normalize_domain(url: str) -> str:
    if not url.startswith("http"):
        url = "http://" + url
    parts = tldextract.extract(url)
    domain = ".".join(part for part in [parts.domain, parts.suffix] if part)
    return f"{domain}"


def _is_valid_url(url: str) -> bool:
    return url.startswith('http') and not any(b in url for b in BLACKLIST)


def _has_platform_fingerprints(html: str) -> bool:
    low = html.lower()
    return any(fp.lower() in low for fp in PLATFORM_FPS)


def _has_shop_paths(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in SHOP_PATH_HINTS)


def _soft_vet(url: str, timeout: float) -> Dict[str, bool]:
    key = _normalize_domain(url)
    # cache check
    try:
        with open(SOFTVET_CACHE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if row.get("domain") == key:
                        return row.get("result", {"has_product_schema": False, "has_cart": False, "has_platform_fp": False})
                except Exception:
                    continue
    except FileNotFoundError:
        pass

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": random.choice(HEADERS_LIST)}) as client:
            r = client.get(url)
            html = r.text or ""
            has_product_schema = '"@type":"Product"' in html or '\"@type\":\"Product\"' in html
            has_cart = any(h in html.lower() for h in ["add to cart", "add-to-cart", "basket"]) \
                       or any(p in r.url.path.lower() for p in SHOP_PATH_HINTS)
            result = {
                "has_product_schema": has_product_schema,
                "has_cart": has_cart,
                "has_platform_fp": _has_platform_fingerprints(html),
            }
            _ensure_cache_dir()
            with open(SOFTVET_CACHE, 'a', encoding='utf-8') as f:
                f.write(json.dumps({"domain": key, "result": result}) + "\n")
            return result
    except Exception:
        return {"has_product_schema": False, "has_cart": False, "has_platform_fp": False}


def _parse_proxy_line(line: str) -> Tuple[Optional[str], Optional[Tuple[str, str]]]:
    # returns (proxy_hostport, (user, pass)) or (proxy, None)
    auth, host = None, None
    if '@' in line:
        creds, addr = line.split('@', 1)
        if ':' in creds:
            user, pwd = creds.split(':', 1)
            auth = (user, pwd)
        host = addr
    else:
        host = line
    return host, auth


def _load_proxies(path: Optional[str]) -> List[Tuple[str, Optional[Tuple[str, str]]]]:
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            hp, auth = _parse_proxy_line(s)
            if hp:
                out.append((hp, auth))
    return out


def _get_driver(headless: bool, proxy_hostport: Optional[str], proxy_auth: Optional[Tuple[str, str]]):
    # Try undetected-chromedriver first, with global init lock to avoid FileExistsError
    try:
        with UC_INIT_LOCK:
            chrome_opts = uc.ChromeOptions()
            if headless:
                chrome_opts.add_argument("--headless=new")
            chrome_opts.add_argument("--window-size=1280,800")
            chrome_opts.add_argument("--disable-gpu")
            chrome_opts.add_argument("--no-sandbox")
            chrome_opts.add_argument("--disable-dev-shm-usage")
            chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
            chrome_opts.add_argument(f"--user-agent={random.choice(HEADERS_LIST)}")
            if proxy_hostport:
                chrome_opts.add_argument(f"--proxy-server=http://{proxy_hostport}")
            driver = uc.Chrome(options=chrome_opts)
    except Exception:
        # Fallback to standard Selenium with bundled driver
        std_opts = StdOptions()
        if headless:
            std_opts.add_argument("--headless=new")
        std_opts.add_argument("--window-size=1280,800")
        std_opts.add_argument("--disable-gpu")
        std_opts.add_argument("--no-sandbox")
        std_opts.add_argument("--disable-dev-shm-usage")
        std_opts.add_argument("--disable-blink-features=AutomationControlled")
        std_opts.add_argument(f"--user-agent={random.choice(HEADERS_LIST)}")
        if proxy_hostport:
            std_opts.add_argument(f"--proxy-server=http://{proxy_hostport}")
        # Use local chromedriver if available
        local_driver = os.path.join("agents", "chromedriver-win64", "chromedriver.exe")
        service = StdService(local_driver) if os.path.exists(local_driver) else None
        driver = std_webdriver.Chrome(service=service, options=std_opts)

    # Note: proxy auth via basic alert isn't handled; requires extension if needed
    return driver


def _engine_selector(engine: str, query: str, page: int) -> str:
    if engine == 'google':
        start = page * 10
        return f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=en&start={start}"
    if engine == 'bing':
        first = page * 10 + 1
        return f"https://www.bing.com/search?q={query.replace(' ', '+')}&first={first}"
    if engine == 'brave':
        return f"https://search.brave.com/search?q={query.replace(' ', '+')}&offset={page*10}"
    return ""


def _extract_serp_domains(driver, engine: str, max_pages: int, pacing: Dict, behavior: Dict, manual_pause: bool) -> List[str]:
    domains: List[str] = []
    base_delay = float(pacing.get('base_delay_seconds', 3.0))
    jitter = float(pacing.get('jitter_seconds', 2.0))
    backoff_mult = float(pacing.get('backoff_multiplier', 1.5))
    max_delay = float(pacing.get('max_delay_seconds', 10.0))
    delay = base_delay

    def humanize():
        if behavior.get('simulate_mouse_scroll', True):
            try:
                ActionChains(driver).move_by_offset(10, 10).perform()
                driver.execute_script("window.scrollBy(0, arguments[0]);", int(behavior.get('scroll_pixels', 600)))
                time.sleep(int(behavior.get('scroll_delay_ms', 300))/1000.0)
            except Exception:
                pass

    for page in range(max_pages):
        url = _engine_selector(engine, "__QUERY__", page)
        if not url:
            break
        # Query placeholder replaced by caller
        yield_url = url
        yield yield_url, domains, delay, humanize, backoff_mult, max_delay, jitter


def _save_query_cache(query: str, engine: str, domains: List[str]):
    _append_jsonl(QUERY_CACHE, {"engine": engine, "query": query, "domains": domains})


def discover_domains(industry: str, max_results: int = 500) -> List[str]:
    cfg = _load_config()
    headless = bool(cfg.get("use_headless", False))
    proxies = _load_proxies(cfg.get("proxy_file"))
    engines = cfg.get("engines", ["google", "bing", "brave"])[:3]
    regions = cfg.get("regions", ["us"])  # used in query generation
    languages = cfg.get("languages", ["en"])  # reserved for future per-engine params
    max_pages = int(cfg.get("max_serp_pages", 5))
    pacing = cfg.get("pacing", {})
    behavior = cfg.get("behavior", {})
    manual_pause = bool(cfg.get("captcha", {}).get("manual_pause", True))
    queries_per_session = int(cfg.get("restarts", {}).get("queries_per_session", 8))

    queries = _generate_queries(industry, regions, languages)

    seen: Set[str] = set()
    out: List[str] = []

    proxy_health: Dict[str, int] = {hp: 0 for hp, _ in proxies}
    proxy_iter = iter(proxies) if proxies else iter([])

    def next_proxy():
        try:
            return next(proxy_iter)
        except StopIteration:
            # recycle best proxies first (lowest health score)
            if not proxy_health:
                return None
            best = sorted(proxy_health.items(), key=lambda kv: kv[1])[0][0]
            return (best, None)

    current_proxy = next_proxy()
    # Branch: use parallel workers if configured, else sequential
    if int(cfg.get("pool", {}).get("drivers", 1)) >= 2:
        # Shared state
        discovered_set = _load_discovered_set()
        completed_query_keys = _load_completed_queries()
        total_tasks = len(queries) * len(engines)
        pbar = tqdm(total=total_tasks, desc="Discovery", unit="query")
        pbar_lock = Lock()
        set_lock = Lock()
        file_lock = Lock()

        # Prepare one queue per engine with queries only
        engine_queues: Dict[str, Queue] = {eng: Queue() for eng in engines}
        total_tasks = 0
        for eng in engines:
            for q in queries:
                key = f"{eng}::{q}"
                if key in completed_query_keys:
                    with pbar_lock:
                        pbar.update(1)
                    continue
                engine_queues[eng].put(q)
                total_tasks += 1
        # reset progress total to actual remaining
        with pbar_lock:
            pbar.total = pbar.n + total_tasks
            pbar.refresh()

        # Proxy iterator per worker
        proxy_iter_global = iter(proxies) if proxies else iter([])
        proxy_health: Dict[str, int] = {hp: 0 for hp, _ in proxies}

        def next_proxy_local():
            try:
                return next(proxy_iter_global)
            except StopIteration:
                if not proxy_health:
                    return None
                best = sorted(proxy_health.items(), key=lambda kv: kv[1])[0][0]
                return (best, None)

        def worker_loop(engine_name: str):
            current_proxy = next_proxy_local()
            driver = _get_driver(headless=headless, proxy_hostport=current_proxy[0] if current_proxy else None, proxy_auth=current_proxy[1] if current_proxy else None)
            # Label window for clarity
            try:
                driver.execute_script(f"document.title = 'OSINT Discover - {engine_name.upper()}'")
            except Exception:
                pass
            queries_run_local = 0
            try:
                while True:
                    try:
                        q = engine_queues[engine_name].get(timeout=0.5)
                    except Empty:
                        break

                    # restart per pacing policy
                    if queries_run_local >= queries_per_session:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        current_proxy = next_proxy_local()
                        driver = _get_driver(headless=headless, proxy_hostport=current_proxy[0] if current_proxy else None, proxy_auth=current_proxy[1] if current_proxy else None)
                        queries_run_local = 0

                    domains_for_query: List[str] = []

                    # iterate SERP pages
                    for templ_url, dom_acc, delay, humanize, backoff_mult, max_delay, jitter in _extract_serp_domains(driver, engine_name, max_pages, pacing, behavior, manual_pause):
                        serp_url = templ_url.replace("__QUERY__", q.replace(' ', '+'))
                        driver.get(serp_url)
                        time.sleep(delay + random.uniform(0, jitter))
                        humanize()

                        page_src = (driver.page_source or "").lower()
                        if ("captcha" in page_src) or ("unusual traffic" in page_src):
                            if manual_pause:
                                try:
                                    input(f"[CAPTCHA][{engine_name}] Solve in the visible window, then press Enter to resume...")
                                except Exception:
                                    pass
                            else:
                                if current_proxy:
                                    proxy_health[current_proxy[0]] = proxy_health.get(current_proxy[0], 0) + 1
                                break

                        # parse containers per engine
                        containers = []
                        if engine_name == 'google':
                            containers = driver.find_elements(By.CSS_SELECTOR, 'div.BToiNc')
                            anchor_sel = 'a'
                        elif engine_name == 'bing':
                            containers = driver.find_elements(By.CSS_SELECTOR, 'li.b_algo')
                            anchor_sel = 'h2 a'
                        else:  # brave
                            containers = driver.find_elements(By.CSS_SELECTOR, 'div.snippet')
                            anchor_sel = 'a'

                        if not containers:
                            delay = min(max_delay, delay * backoff_mult)
                            continue

                        page_domains: List[str] = []
                        for c in containers:
                            try:
                                a = c.find_element(By.CSS_SELECTOR, anchor_sel)
                                href = (a.get_attribute('href') or '').strip()
                                if not _is_valid_url(href):
                                    continue
                                d = _normalize_domain(href)
                                if d:
                                    page_domains.append(d)
                            except Exception:
                                continue

                        # accumulate with shared de-dup
                        for d in page_domains:
                            with set_lock:
                                if d in seen:
                                    continue
                            url = f"https://{d}"
                            sv = _soft_vet(url, timeout=float(cfg.get("soft_vetting", {}).get("timeout_seconds", 8)))
                            if not (sv["has_cart"] or sv["has_product_schema"] or sv["has_platform_fp"] or _has_shop_paths(url)):
                                continue
                            with set_lock:
                                if d in seen:
                                    continue
                                seen.add(d)
                            with file_lock:
                                if len(out) < max_results:
                                    out.append(d)
                                _append_jsonl(DISCOVERED_JSONL, {"domain": d, "engine": engine_name, "query": q, "ts": int(time.time())})
                            domains_for_query.append(d)
                            if len(out) >= max_results:
                                break

                        if len(out) >= max_results:
                            break

                        delay = max(float(pacing.get('base_delay_seconds', 3.0)), delay * 0.9)

                    _save_query_cache(q, engine_name, domains_for_query)
                    with pbar_lock:
                        pbar.update(1)
                    queries_run_local += 1
                    if len(out) >= max_results:
                        break
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass

        # Launch one worker per engine (up to 3)
        threads: List[Thread] = []
        for idx, eng in enumerate(engines):
            t = Thread(target=worker_loop, name=f"worker-{eng}", args=(eng, ))
            t.daemon = True
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        try:
            pbar.close()
        except Exception:
            pass
        return out
    else:
        # Fallback to sequential (existing logic) if pool disabled
        current_proxy = next_proxy()
        driver = _get_driver(headless=headless, proxy_hostport=current_proxy[0] if current_proxy else None, proxy_auth=current_proxy[1] if current_proxy else None)

        # Resume state
        discovered_set = _load_discovered_set()
        completed_query_keys = _load_completed_queries()
        total_tasks = len(queries) * len(engines)
        pbar = tqdm(total=total_tasks, desc="Discovery", unit="query")

        queries_run = 0

        try:
            for engine in engines:
                for q in queries:
                    key = f"{engine}::{q}"
                    if key in completed_query_keys:
                        pbar.update(1)
                        continue
                    if queries_run >= queries_per_session:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        current_proxy = next_proxy()
                        driver = _get_driver(headless=headless, proxy_hostport=current_proxy[0] if current_proxy else None, proxy_auth=current_proxy[1] if current_proxy else None)
                        queries_run = 0

                    domains_for_query: List[str] = []
                    for templ_url, dom_acc, delay, humanize, backoff_mult, max_delay, jitter in _extract_serp_domains(driver, engine, max_pages, pacing, behavior, manual_pause):
                        serp_url = templ_url.replace("__QUERY__", q.replace(' ', '+'))
                        driver.get(serp_url)
                        time.sleep(delay + random.uniform(0, jitter))
                        humanize()

                        page_src = (driver.page_source or "").lower()
                        if ("captcha" in page_src) or ("unusual traffic" in page_src):
                            if manual_pause:
                                try:
                                    input("[CAPTCHA] Please solve in the browser, then press Enter...")
                                except Exception:
                                    pass
                            else:
                                if current_proxy:
                                    proxy_health[current_proxy[0]] = proxy_health.get(current_proxy[0], 0) + 1
                                break

                        containers = []
                        if engine == 'google':
                            containers = driver.find_elements(By.CSS_SELECTOR, 'div.BToiNc')
                            anchor_sel = 'a'
                        elif engine == 'bing':
                            containers = driver.find_elements(By.CSS_SELECTOR, 'li.b_algo')
                            anchor_sel = 'h2 a'
                        else:
                            containers = driver.find_elements(By.CSS_SELECTOR, 'div.snippet')
                            anchor_sel = 'a'

                        if not containers:
                            delay = min(max_delay, delay * backoff_mult)
                            continue

                        page_domains: List[str] = []
                        for c in containers:
                            try:
                                a = c.find_element(By.CSS_SELECTOR, anchor_sel)
                                href = (a.get_attribute('href') or '').strip()
                                if not _is_valid_url(href):
                                    continue
                                d = _normalize_domain(href)
                                if d:
                                    page_domains.append(d)
                            except Exception:
                                continue

                        for d in page_domains:
                            if d not in seen:
                                url = f"https://{d}"
                                sv = _soft_vet(url, timeout=float(cfg.get("soft_vetting", {}).get("timeout_seconds", 8)))
                                if not (sv["has_cart"] or sv["has_product_schema"] or sv["has_platform_fp"] or _has_shop_paths(url)):
                                    continue
                                seen.add(d)
                                out.append(d)
                                if d not in discovered_set:
                                    _append_jsonl(DISCOVERED_JSONL, {"domain": d, "engine": engine, "query": q, "ts": int(time.time())})
                                    discovered_set.add(d)
                                domains_for_query.append(d)
                                if len(out) >= max_results:
                                    _save_query_cache(q, engine, domains_for_query)
                                    pbar.update(1)
                                    pbar.close()
                                    return out

                        delay = max(float(pacing.get('base_delay_seconds', 3.0)), delay * 0.9)

                    _save_query_cache(q, engine, domains_for_query)
                    queries_run += 1
                    pbar.update(1)

            return out
        finally:
            try:
                pbar.close()
            except Exception:
                pass
            try:
                driver.quit()
            except Exception:
                pass
