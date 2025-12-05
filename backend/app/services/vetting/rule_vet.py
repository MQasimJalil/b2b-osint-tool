import os
import json
import re
from typing import Dict, Set, Tuple, List

import httpx

CACHE_DIR = os.path.join("pipeline", "cache")
SOFTVET_CACHE = os.path.join(CACHE_DIR, "softvet_cache.jsonl")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CANDIDATE_PATHS = ["/", "/shop", "/products", "/collections", "/store", "/contact", "/about"]

PLATFORM_HINTS = [
    "cdn.shopify.com", "woocommerce", "/wp-json/wc/", "wp-content/plugins/woocommerce", "bigcommerce"
]

SHOP_PATH_HINTS = ["/cart", "/checkout", "/product", "/products", "/collections", "/shop"]


def _load_softvet_map() -> Dict[str, Dict[str, bool]]:
    m: Dict[str, Dict[str, bool]] = {}
    try:
        with open(SOFTVET_CACHE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                    dom = row.get("domain")
                    res = row.get("result") or {}
                    if isinstance(dom, str):
                        m[dom] = {
                            "has_product_schema": bool(res.get("has_product_schema")),
                            "has_cart": bool(res.get("has_cart")),
                            "has_platform_fp": bool(res.get("has_platform_fp")),
                        }
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return m


def _fetch_html(domain: str, timeout: float = 8.0) -> str:
    base = f"https://{domain}"
    try:
        with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            for p in CANDIDATE_PATHS:
                try:
                    r = client.get(base + p)
                    if r.status_code < 400 and r.text:
                        return r.text
                except Exception:
                    continue
    except Exception:
        return ""
    return ""


def _rule_yes(html: str, url: str) -> bool:
    low = html.lower()
    if any(kw in low for kw in PLATFORM_HINTS):
        return True
    if any(p in url.lower() for p in SHOP_PATH_HINTS):
        return True
    if '"@type":"Product"' in low or '\\"@type\\":\\"Product\\"' in low:
        return True
    return False


def _rule_no(html: str) -> bool:
    low = html.lower()
    if all(tok not in low for tok in ["product", "cart", "checkout", "shop", "store"]):
        return True
    if any(h in low for h in ["add to cart", "add-to-cart", "basket"]):
        return False
    return False


def rule_vet(domains: List[str]) -> Tuple[Set[str], Set[str], Set[str]]:
    soft = _load_softvet_map()
    auto_yes: Set[str] = set()
    auto_no: Set[str] = set()
    unclear: Set[str] = set()

    for d in domains:
        sv = soft.get(d)
        if sv and (sv.get("has_cart") or sv.get("has_product_schema") or sv.get("has_platform_fp")):
            auto_yes.add(d)
            continue
        html = _fetch_html(d)
        if not html:
            auto_no.add(d)
            continue
        if _rule_yes(html, f"https://{d}"):
            auto_yes.add(d)
        elif _rule_no(html):
            auto_no.add(d)
        else:
            unclear.add(d)
    return auto_yes, auto_no, unclear
