import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastmcp import FastMCP

from pipeline.rag import query_rag, _get_chroma_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).parent
EXTRACTED_DIR = BASE_DIR / "extracted_data" / "companies"
CRAWLED_STATE_DIR = BASE_DIR / "crawled_data" / "crawl_state"
EMBED_TRACK_FILE = BASE_DIR / "rag_data" / ".embedded_domains.jsonl"


app = FastMCP("b2b-osint-mcp-stdio")


@app.tool()
def market_search(query: str, n_results: int = 5) -> Dict[str, List[Dict]]:
    """Basic semantic search across raw_pages, products, and companies collections.

    - query: Natural language query
    - n_results: Number of results to return (1-100)
    """
    # Validate query
    if not query or not query.strip():
        return {"results": [], "error": "Query cannot be empty"}

    n = max(1, min(int(n_results), 100))
    results = query_rag(query, top_k=n)
    return {"results": results}


@app.tool()
def filter_search(query: str, key: str, value: str, n_results: int = 5) -> Dict[str, List[Dict]]:
    """Semantic search with a metadata filter (key in: domain | brand | category | company)."""
    # Validate query
    if not query or not query.strip():
        return {"results": [], "error": "Query cannot be empty"}

    # Validate filter key
    valid_keys = ["domain", "brand", "category", "company"]
    if key not in valid_keys:
        return {"results": [], "error": f"Invalid filter key '{key}'. Must be one of: {', '.join(valid_keys)}"}

    n = max(1, min(int(n_results), 100))
    results = query_rag(query, filters={key: value}, top_k=n)
    return {"results": results}


@app.tool()
def get_domains() -> Dict[str, List[str]]:
    """List distinct domains available (prefers embedded tracker; falls back to extracted data or Chroma)."""
    domains: List[str] = []

    if EMBED_TRACK_FILE.exists():
        try:
            seen = set()
            with EMBED_TRACK_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    d = rec.get("domain")
                    if d and d not in seen:
                        seen.add(d)
                        domains.append(d)
        except Exception as e:
            logger.warning(f"Error reading embedded tracker file: {e}")

    if not domains and EXTRACTED_DIR.exists():
        try:
            domains = sorted([p.name for p in EXTRACTED_DIR.iterdir() if p.is_dir()])
        except Exception as e:
            logger.warning(f"Error reading extracted data directory: {e}")

    if not domains:
        try:
            client = _get_chroma_client()
            for coll_name in ["raw_pages", "products", "companies"]:
                try:
                    coll = client.get_collection(coll_name)
                    got = coll.get(include=["metadatas"])
                    for md in (got.get("metadatas") or []):
                        d = md.get("domain")
                        if d and d not in domains:
                            domains.append(d)
                except Exception as e:
                    logger.warning(f"Error accessing collection {coll_name}: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error connecting to ChromaDB: {e}")

    return {"domains": domains}


@app.tool()
def get_contacts() -> Dict[str, List[Dict]]:
    """Return structured contacts and related profile fields per domain when available."""
    contacts: List[Dict] = []
    if not EXTRACTED_DIR.exists():
        return {"contacts": contacts}
    try:
        for domain_dir in EXTRACTED_DIR.iterdir():
            if not domain_dir.is_dir():
                continue
            profile_path = domain_dir / "profile.json"
            if not profile_path.exists():
                continue
            try:
                with profile_path.open("r", encoding="utf-8") as f:
                    profile = json.load(f)
                entry = {
                    "domain": domain_dir.name,
                    "company": profile.get("company"),
                    "main_contacts": profile.get("main_contacts") or {},
                    "social": profile.get("social") or {},
                    "management": profile.get("management") or [],
                }
                contacts.append(entry)
            except Exception as e:
                logger.warning(f"Error reading profile for {domain_dir.name}: {e}")
                continue
    except Exception as e:
        logger.warning(f"Error iterating extracted data directory: {e}")
    return {"contacts": contacts}


@app.tool()
def get_stats() -> Dict[str, object]:
    """Return counts per collection, domain count, and embedded date range."""
    stats: Dict[str, object] = {"collections": {}, "domains": 0, "embedded_range": {"min": None, "max": None}}

    try:
        client = _get_chroma_client()
        for coll_name in ["raw_pages", "products", "companies"]:
            try:
                coll = client.get_collection(coll_name)
                stats["collections"][coll_name] = coll.count()
            except Exception as e:
                logger.warning(f"Error getting count for collection {coll_name}: {e}")
                stats["collections"][coll_name] = 0
    except Exception as e:
        logger.warning(f"Error connecting to ChromaDB: {e}")
        stats["collections"] = {"raw_pages": 0, "products": 0, "companies": 0}

    domains = set()
    min_ts = None
    max_ts = None
    if EMBED_TRACK_FILE.exists():
        try:
            with EMBED_TRACK_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    d = rec.get("domain")
                    if d:
                        domains.add(d)
                    t = rec.get("embedded_at")
                    if t:
                        try:
                            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
                            min_ts = dt if (min_ts is None or dt < min_ts) else min_ts
                            max_ts = dt if (max_ts is None or dt > max_ts) else max_ts
                        except Exception as e:
                            logger.debug(f"Error parsing timestamp {t}: {e}")
        except Exception as e:
            logger.warning(f"Error reading embedded tracker file: {e}")

    if not domains and EXTRACTED_DIR.exists():
        try:
            domains = {p.name for p in EXTRACTED_DIR.iterdir() if p.is_dir()}
        except Exception as e:
            logger.warning(f"Error reading extracted data directory: {e}")

    stats["domains"] = len(domains)
    stats["embedded_range"] = {
        "min": min_ts.isoformat() if min_ts else None,
        "max": max_ts.isoformat() if max_ts else None,
    }
    return stats


@app.tool()
def get_recent_crawls(limit: int = 10) -> Dict[str, List[Dict]]:
    """Show last crawl activity from crawl_state files (timestamp + sample of URLs)."""
    entries: List[Dict] = []
    if not CRAWLED_STATE_DIR.exists():
        return {"recent": entries}
    try:
        files = sorted(
            [p for p in CRAWLED_STATE_DIR.iterdir() if p.is_file() and p.name.endswith("_visited.txt")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in files[: max(1, min(int(limit), 100))]:
            domain = p.name.replace("_visited.txt", "")
            ts = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
            urls: List[str] = []
            try:
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        urls.append(line)
                        if len(urls) > 50:
                            urls.pop(0)
            except Exception as e:
                logger.warning(f"Error reading crawl state file {p.name}: {e}")
            entries.append({"domain": domain, "timestamp": ts, "sample_urls_tail": urls[-5:]})
    except Exception as e:
        logger.warning(f"Error accessing crawled state directory: {e}")
    return {"recent": entries}


if __name__ == "__main__":
    # Start stdio MCP server
    app.run()


