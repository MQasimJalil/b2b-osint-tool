import os
import json
import gzip
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# Reuse existing RAG utilities and Chroma connection
from pipeline.rag import query_rag, _get_chroma_client, RAG_DATA_DIR

BASE_DIR = Path(__file__).parent
EXTRACTED_DIR = BASE_DIR / "extracted_data" / "companies"
CRAWLED_STATE_DIR = BASE_DIR / "crawled_data" / "crawl_state"
EMBED_TRACK_FILE = BASE_DIR / "rag_data" / ".embedded_domains.jsonl"


class MarketSearchRequest(BaseModel):
    query: str = Field(..., description="Semantic query string")
    n_results: int = Field(5, ge=1, le=100, description="Number of results to return")


class FilterSearchRequest(BaseModel):
    query: str = Field(..., description="Semantic query string")
    key: str = Field(..., description="Metadata key to filter on (e.g., domain, brand, category, company)")
    value: str = Field(..., description="Metadata value to match")
    n_results: int = Field(5, ge=1, le=100, description="Number of results to return")


app = FastAPI(title="B2B OSINT MCP Server", version="0.1.0")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/market_search")
def market_search(req: MarketSearchRequest) -> Dict[str, List[Dict]]:
    try:
        results = query_rag(req.query, top_k=req.n_results)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/filter_search")
def filter_search(req: FilterSearchRequest) -> Dict[str, List[Dict]]:
    try:
        filters = {req.key: req.value}
        results = query_rag(req.query, filters=filters, top_k=req.n_results)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/tools/domains")
def get_domains() -> Dict[str, List[str]]:
    domains: List[str] = []

    # Prefer domains that have been embedded (present in tracker)
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
        except Exception:
            pass

    # Fallback to directories in extracted_data/companies
    if not domains and EXTRACTED_DIR.exists():
        try:
            domains = sorted([p.name for p in EXTRACTED_DIR.iterdir() if p.is_dir()])
        except Exception:
            pass

    # Fallback to distinct domains in Chroma metadatas (may be slower)
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
                except Exception:
                    continue
        except Exception:
            pass

    return {"domains": domains}


@app.get("/tools/contacts")
def get_contacts() -> Dict[str, List[Dict]]:
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
            except Exception:
                continue
    except Exception:
        pass
    return {"contacts": contacts}


@app.get("/tools/stats")
def get_stats() -> Dict[str, object]:
    stats: Dict[str, object] = {
        "collections": {},
        "domains": 0,
        "embedded_range": {"min": None, "max": None},
    }

    # Collection counts
    try:
        client = _get_chroma_client()
        for coll_name in ["raw_pages", "products", "companies"]:
            try:
                coll = client.get_collection(coll_name)
                got = coll.count()
                stats["collections"][coll_name] = got
            except Exception:
                stats["collections"][coll_name] = 0
    except Exception:
        stats["collections"] = {"raw_pages": 0, "products": 0, "companies": 0}

    # Domains and date range from embedded tracker
    domains = set()
    min_ts: Optional[datetime] = None
    max_ts: Optional[datetime] = None
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
                        except Exception:
                            pass
        except Exception:
            pass

    # Fallback domain counting via extracted directories
    if not domains and EXTRACTED_DIR.exists():
        try:
            domains = {p.name for p in EXTRACTED_DIR.iterdir() if p.is_dir()}
        except Exception:
            pass

    stats["domains"] = len(domains)
    stats["embedded_range"] = {
        "min": min_ts.isoformat() if min_ts else None,
        "max": max_ts.isoformat() if max_ts else None,
    }
    return stats


@app.get("/tools/recent_crawls")
def get_recent_crawls(limit: int = Query(10, ge=1, le=100)) -> Dict[str, List[Dict]]:
    entries: List[Dict] = []
    if not CRAWLED_STATE_DIR.exists():
        return {"recent": entries}
    try:
        files = sorted(
            [p for p in CRAWLED_STATE_DIR.iterdir() if p.is_file() and p.name.endswith("_visited.txt")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in files[:limit]:
            domain = p.name.replace("_visited.txt", "")
            ts = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
            urls: List[str] = []
            try:
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        # Heuristic: line might be URL or prefixed with metadata; keep raw
                        urls.append(line)
                        if len(urls) > 50:
                            urls.pop(0)
            except Exception:
                pass
            entries.append({"domain": domain, "timestamp": ts, "sample_urls_tail": urls[-5:]})
    except Exception:
        pass
    return {"recent": entries}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("mcp_server:app", host="0.0.0.0", port=port, reload=False)


