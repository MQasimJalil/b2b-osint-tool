import os
import gzip
import json
import time
import asyncio
import random
import hashlib
from typing import List, Dict, Set, Tuple, Optional
from urllib.parse import urlparse, urljoin, urldefrag
from urllib import robotparser

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from tqdm import tqdm
from pipeline.deduplicate import track_crawled_domain, save_homepage_features, extract_homepage_features


SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff",
    ".svg", ".ico", ".zip", ".rar", ".7z", ".tar", ".gz", ".pdf"
}


def _host(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _canonical(u: str) -> str:
    u, _ = urldefrag(u)
    if u.endswith('/'):
        u = u.rstrip('/')
    return u


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _paths(out_dir: str, base_url: str):
    host = _host(base_url).replace(':', '_')
    domains_dir = os.path.join(out_dir, "domains")
    state_dir = os.path.join(out_dir, "crawl_state")
    os.makedirs(domains_dir, exist_ok=True)
    os.makedirs(state_dir, exist_ok=True)
    return (
        os.path.join(domains_dir, f"{host}.jsonl.gz"),
        os.path.join(state_dir, f"{host}_visited.txt"),
        os.path.join(state_dir, f"{host}_hashes.txt"),
        os.path.join(state_dir, f"{host}_complete.txt"),  # Completion marker
    )


def is_domain_fully_crawled(domain: str, output_dir: str = "crawled_data", min_pages: int = 5) -> bool:
    """
    Check if a domain has been FULLY crawled (completion marker exists).
    Returns True only if the crawl completed successfully.
    Partially crawled domains (interrupted mid-way) will return False.
    """
    base_url = f"https://{domain}"
    out_path, visited_path, hashes_path, complete_path = _paths(output_dir, base_url)
    
    # Only consider domain "fully crawled" if completion marker exists
    if os.path.exists(complete_path):
        return True
    
    return False


def get_crawl_status(domains: List[str], output_dir: str = "crawled_data") -> Dict[str, Dict]:
    """
    Get crawl status for a list of domains.
    Returns dict with domain -> {fully_crawled: bool, pages: int, visited_urls: int, in_progress: bool}
    """
    status = {}
    for domain in domains:
        base_url = f"https://{domain}"
        out_path, visited_path, hashes_path, complete_path = _paths(output_dir, base_url)
        
        pages = 0
        visited = 0
        fully_crawled = os.path.exists(complete_path)
        
        if os.path.exists(out_path):
            try:
                with gzip.open(out_path, 'rt', encoding='utf-8') as f:
                    pages = sum(1 for _ in f)
            except Exception:
                pass
        
        if os.path.exists(visited_path):
            visited = len(_load_set(visited_path))
        
        # In-progress = has some data but no completion marker
        in_progress = (pages > 0 or visited > 0) and not fully_crawled
        
        status[domain] = {
            "fully_crawled": fully_crawled,
            "pages": pages,
            "visited_urls": visited,
            "in_progress": in_progress
        }
    
    return status


def _load_set(path: str) -> Set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _save_set(path: str, data: Set[str]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for item in data:
            f.write(item + "\n")
    os.replace(tmp, path)


async def _fetch_page(crawler, url: str, depth: int, host: str) -> Optional[Dict]:
    """Fetch a single page and return parsed result."""
    try:
        cfg = CrawlerRunConfig(
            excluded_tags=[] if depth == 0 else ['form', 'header', 'footer', 'nav'],
            css_selector="body",
            exclude_external_links=True,
            exclude_external_images=True,
        )
        res = await crawler.arun(url, config=cfg)
        
        text = (res.markdown or "").strip()
        if not text:
            return None
        
        return {
            "url": url,
            "domain": host,
            "title": getattr(res, 'title', None),
            "content": text,
            "content_hash": _sha256_text(text),
            "depth": depth,
            "ts": int(time.time()),
            "links": res.links.get("internal", []) if res.links else []
        }
    except Exception:
        return None


async def _crawl_one(base_url: str, out_path: str, visited_path: str, hashes_path: str,
                     complete_path: str, max_pages: int = 200, max_depth: int = 2, 
                     retry_on_zero: bool = True, pbar: Optional[tqdm] = None, concurrency: int = 5):
    """
    Crawl a single domain with concurrent page fetching.
    Resumes from existing state if crawl was interrupted.
    Writes completion marker only when crawl finishes successfully.
    
    Args:
        concurrency: Number of pages to fetch in parallel (default: 5)
    """
    visited: Set[str] = _load_set(visited_path)
    content_hashes: Set[str] = _load_set(hashes_path)
    queue: List[Tuple[str, int]] = [(base_url, 0)] if base_url not in visited else []
    
    host = _host(base_url)
    robots: Optional[robotparser.RobotFileParser] = None
    
    # Load robots.txt
    try:
        rp = robotparser.RobotFileParser()
        root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
        rp.set_url(urljoin(root, "/robots.txt"))
        rp.read()
        robots = rp
    except Exception:
        pass

    attempt = 0
    max_attempts = 2 if retry_on_zero else 1
    
    while attempt < max_attempts:
        pages_found = 0
        attempt += 1
        
        async with AsyncWebCrawler() as crawler:
            while queue and len(visited) < max_pages:
                # Prepare batch of URLs to fetch concurrently
                batch = []
                while queue and len(batch) < concurrency and len(visited) + len(batch) < max_pages:
                    url, depth = queue.pop(0)
                    url = _canonical(url)
                    
                    # Skip if already visited
                    if url in visited:
                        continue
                    
                    # Skip unwanted extensions
                    parsed = urlparse(url)
                    if os.path.splitext(parsed.path.lower())[1] in SKIP_EXTENSIONS:
                        continue
                    
                    # Check robots.txt
                    if robots and not robots.can_fetch("*", url):
                        continue
                    
                    # Add to batch
                    batch.append((url, depth))
                    visited.add(url)
                
                if not batch:
                    break
                
                # Fetch pages concurrently
                tasks = [_fetch_page(crawler, url, depth, host) for url, depth in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for (url, depth), result in zip(batch, results):
                    if isinstance(result, Exception) or result is None:
                        continue
                    
                    h = result["content_hash"]
                    if h not in content_hashes:
                        content_hashes.add(h)
                        pages_found += 1
                        
                        # Save page (without links)
                        row = {k: v for k, v in result.items() if k != "links"}
                        with gzip.open(out_path, 'at', encoding='utf-8') as f:
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    
                    # Extract links for next depth
                    if depth < max_depth:
                        for link in result.get("links", []):
                            href = link.get('href')
                            if not href:
                                continue
                            nxt = _canonical(urljoin(url, href))
                            if _host(nxt) != host:
                                continue
                            if nxt not in visited:
                                queue.append((nxt, depth + 1))
                
                # Save state after every batch (crash-safe!)
                _save_set(visited_path, visited)
                _save_set(hashes_path, content_hashes)
                
                # Polite delay between batches
                await asyncio.sleep(random.uniform(0.2, 0.5))
        
        # Save final state
        _save_set(visited_path, visited)
        _save_set(hashes_path, content_hashes)
        
    # Write completion marker - domain is fully crawled!
    with open(complete_path, 'w', encoding='utf-8') as f:
        f.write(f"Completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total URLs visited: {len(visited)}\n")
        f.write(f"Unique pages: {len(content_hashes)}\n")

    # Track this domain as crawled for deduplication
    track_crawled_domain(host)

    # Extract and cache homepage features for future deduplication
    try:
        # Find homepage in crawled pages
        homepage_url = base_url
        # Read from crawled data to extract homepage
        with gzip.open(out_path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    page = json.loads(line)
                    if page.get('depth') == 0:  # Homepage
                        # Create pseudo-HTML from content for feature extraction
                        html_content = f"<html><head><title>{page.get('title', '')}</title></head><body>{page.get('content', '')}</body></html>"
                        features = extract_homepage_features(html_content, host, method="regex")
                        save_homepage_features(host, features)
                        break
                except:
                    continue
    except Exception as e:
        # Not critical if we can't extract features now, will fetch later if needed
        pass

    if pbar:
        pbar.write(f"[{host}] ✓ COMPLETE: {len(visited)} URLs, {len(content_hashes)} unique pages")
        pbar.update(1)  # Mark this domain as complete
    else:
        print(f"[{host}] ✓ COMPLETE: {len(visited)} URLs, {len(content_hashes)} unique pages")


def crawl_domains(domains: List[str], output_dir: str = "crawled_data", max_pages: int = 2000, 
                  max_depth: int = 3, skip_crawled: bool = True, concurrency: int = 5,
                  max_parallel_domains: int = 3):
    """
    Crawl multiple domains with progress tracking and concurrent page fetching.
    
    Args:
        domains: List of domains to crawl
        output_dir: Base directory for crawled data
        max_pages: Max pages to crawl per domain
        max_depth: Max depth to crawl (e.g., 3 for home→shop→products)
        skip_crawled: If True, skip domains that already have sufficient crawled data
        concurrency: Number of pages to fetch concurrently per domain (default: 5)
                     Higher values = faster crawling but more aggressive
                     Recommended: 3-10 depending on target site capacity
        max_parallel_domains: Max domains to crawl simultaneously (default: 3)
                              Total concurrent requests = max_parallel_domains × concurrency
                              Keep low to avoid memory issues (1-5 recommended)
    """
    # Filter out already-crawled domains if requested
    if skip_crawled:
        to_crawl = [d for d in domains if not is_domain_fully_crawled(d, output_dir)]
        skipped = len(domains) - len(to_crawl)
        if skipped > 0:
            print(f"Skipping {skipped} already-crawled domains. Crawling {len(to_crawl)} remaining.")
    else:
        to_crawl = domains
    
    if not to_crawl:
        print("All domains already crawled!")
        return
    
    # Create progress bar
    pbar = tqdm(total=len(to_crawl), desc="Crawling domains", unit="domain")
    
    async def worker(queue: asyncio.Queue):
        """Worker that processes domains from the queue."""
        while True:
            try:
                domain = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check if queue is done
                if queue.empty():
                    break
                continue
            
            if domain is None:  # Poison pill
                break
            
            try:
                base = f"https://{domain}"
                out, visited, hashes, complete = _paths(output_dir, base)
                await _crawl_one(base, out, visited, hashes, complete, max_pages=max_pages, 
                               max_depth=max_depth, pbar=pbar, concurrency=concurrency)
            except Exception as e:
                pbar.write(f"[ERROR] Failed to crawl {domain}: {e}")
            finally:
                queue.task_done()
    
    async def runner():
        # Create queue and add all domains
        queue = asyncio.Queue()
        for domain in to_crawl:
            await queue.put(domain)
        
        # Start worker pool (max_parallel_domains workers)
        workers = [asyncio.create_task(worker(queue)) for _ in range(max_parallel_domains)]
        
        # Wait for all domains to be processed
        await queue.join()
        
        # Stop workers
        for _ in range(max_parallel_domains):
            await queue.put(None)  # Poison pill
        await asyncio.gather(*workers)

    # Handle both cases: running from async context (Streamlit) or sync context (main.py)
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
        # If we're here, there's a running loop (e.g., Streamlit)
        # We need to run in a separate thread with its own event loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, runner())
            future.result()  # Wait for completion
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        asyncio.run(runner())

    pbar.close()
