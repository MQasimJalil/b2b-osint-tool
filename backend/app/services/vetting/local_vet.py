import os
import re
import json
import time
import subprocess
from typing import List, Dict, Tuple

import httpx

CACHE_DIR = os.path.join("pipeline", "cache")
LOCAL_VET_JSONL = os.path.join(CACHE_DIR, "local_vet_results.jsonl")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CANDIDATE_PATHS = ["/", "/shop", "/products", "/collections", "/store", "/contact", "/about"]
MAX_TOTAL_CHARS = 8000


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _clean_text(html: str) -> str:
    # strip scripts/styles
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
    # drop nav/footer boilerplate heuristics
    html = re.sub(r"\b(privacy policy|terms of service|cookie|subscribe|newsletter)\b", " ", html, flags=re.IGNORECASE)
    # remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fetch_trimmed(domain: str, timeout: float = 10.0) -> str:
    base = f"https://{domain}"
    buf = []
    with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
        try:
            r = client.get(base)
            if r.status_code >= 400:
                return ""
            text = _clean_text(r.text or "")
            if not text:
                return ""
            buf.append(f"# /\n{text[:MAX_TOTAL_CHARS]}")
        except Exception:
            return ""
    return "\n\n".join(buf)


PROMPT_TEMPLATE = (
    """You are a strict vetting assistant.
        Decide YES or NO — does this website directly sell or promote the sale of football (soccer) gear, especially goalkeeper gloves, to consumers, teams, or distributors?

        Rules:
        1. Count it as YES if the content shows or describes products for sale, shopping/cart/checkout features, or buy/contact-for-order options.
        2. Count it as NO if the site only contains news, reviews, training services, clubs, blogs, agencies, or marketplaces without selling its own gear.
        3. Focus on the website’s main intent, not single mentions.

        Output format:
        YES or NO

        CONTENT:\n{content}\n"""
)


def _ollama_run(model: str, prompt: str) -> str:
    # Call local ollama; expect short YES or NO
    proc = subprocess.run(["ollama", "run", model], input=prompt.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = (proc.stdout or b"").decode("utf-8", errors="ignore").strip()
    # take last non-empty line
    line = [ln.strip() for ln in out.splitlines() if ln.strip()]
    raw = (line[-1] if line else "").upper()
    decision = "YES" if "YES" in raw and "NO" not in raw else "NO"
    return decision


def vet_domains_locally(domains: List[str], model: str = "mistral", max_sites: int | None = None) -> List[Dict]:
    _ensure_cache_dir()
    results: List[Dict] = []
    count = 0
    for d in domains:
        if max_sites is not None and count >= max_sites:
            break
        content = _fetch_trimmed(d)
        if not content:
            decision = "NO"
        else:
            prompt = PROMPT_TEMPLATE.format(content=content[:MAX_TOTAL_CHARS])
            try:
                decision = _ollama_run(model, prompt)
            except Exception:
                decision = "NO"
        row = {"domain": d, "decision": decision, "ts": int(time.time())}
        results.append(row)
        # append immediately for crash-safety
        with open(LOCAL_VET_JSONL, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row) + "\n")
        count += 1
    return results
