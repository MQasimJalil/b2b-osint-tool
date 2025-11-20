import os
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from pipeline.rag import query_rag, _get_chroma_client

# Paths to data
EXTRACTED_DATA_DIR = "extracted_data"
INDEXES_DIR = os.path.join(EXTRACTED_DATA_DIR, "indexes")
COMPANIES_FILE = os.path.join(INDEXES_DIR, "all_companies.jsonl")
PRODUCTS_FILE = os.path.join(INDEXES_DIR, "all_products.jsonl")

BASE_DIR = Path(__file__).parent.parent
EXTRACTED_DIR = BASE_DIR / "extracted_data" / "companies"
CRAWLED_STATE_DIR = BASE_DIR / "crawled_data" / "crawl_state"
EMBED_TRACK_FILE = BASE_DIR / "rag_data" / ".embedded_domains.jsonl"

def get_company_profile(domain: str) -> Dict:
    """
    Retrieve structured company profile for a specific domain.
    Reads from all_companies.jsonl.
    """
    if not os.path.exists(COMPANIES_FILE):
        return {"error": "Company index not found. Run extraction first."}

    try:
        with open(COMPANIES_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("domain") == domain:
                        return data
                except:
                    continue
        return {"error": f"Company profile not found for {domain}"}
    except Exception as e:
        return {"error": f"Error reading company file: {str(e)}"}


def get_smykm_notes(domain: str) -> Dict:
    """
    Retrieve SMYKM (Show me you know me) notes for a specific domain.
    These are key insights about the company's unique value proposition, culture, and differentiators.
    Reads from the domain's profile.json file.

    Args:
        domain: The domain name (e.g., "theoneglove.com")

    Returns:
        Dict with 'domain', 'company', 'smykm_notes' (list of insights), and 'description'
    """
    profile_path = EXTRACTED_DIR / domain / "profile.json"

    if not profile_path.exists():
        return {
            "error": f"Profile not found for {domain}",
            "domain": domain,
            "smykm_notes": []
        }

    try:
        with profile_path.open('r', encoding='utf-8') as f:
            profile = json.load(f)

        return {
            "domain": domain,
            "company": profile.get("company", ""),
            "description": profile.get("description", ""),
            "smykm_notes": profile.get("smykm_notes", []),
            "extracted_at": profile.get("extracted_at", "")
        }
    except Exception as e:
        return {
            "error": f"Error reading profile for {domain}: {str(e)}",
            "domain": domain,
            "smykm_notes": []
        }

def get_product_catalog(domain: str) -> List[Dict]:
    """
    Retrieve full product catalog for a specific domain.
    Reads from all_products.jsonl.
    """
    if not os.path.exists(PRODUCTS_FILE):
        return [{"error": "Product index not found. Run extraction first."}]
    
    products = []
    try:
        with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("domain") == domain:
                        products.append(data)
                except:
                    continue
        return products
    except Exception as e:
        return [{"error": f"Error reading product file: {str(e)}"}]

def analyze_pricing_strategy(domain: str) -> Dict:
    """
    Analyze pricing strategy for a domain based on extracted products.
    Returns average price, min/max, and price range distribution.
    """
    products = get_product_catalog(domain)
    if not products or "error" in products[0]:
        return {"error": "No products found to analyze."}
    
    prices = []
    for p in products:
        price_str = str(p.get("price", ""))
        # Clean price string
        clean = ''.join(c for c in price_str if c.isdigit() or c == '.')
        try:
            val = float(clean)
            if val > 0:
                prices.append(val)
        except:
            continue
            
    if not prices:
        return {"error": "No valid prices found."}
    
    return {
        "domain": domain,
        "product_count": len(prices),
        "average_price": round(sum(prices) / len(prices), 2),
        "min_price": min(prices),
        "max_price": max(prices),
        "price_range": f"{min(prices)} - {max(prices)}"
    }

def find_competitors(domain: str, industry: str = "goalkeeper gloves") -> List[Dict]:
    """
    Find potential competitors using RAG semantic search.
    Searches for similar companies in the 'companies' collection.
    """
    query = f"competitors for {domain} in {industry} industry"

    # Query RAG 'companies' collection
    results = query_rag(
        query=query,
        collection_names=["companies"],
        top_k=5
    )

    competitors = []
    seen_domains = set()
    seen_domains.add(domain) # Exclude self

    for r in results:
        meta = r.get("metadata", {})
        comp_domain = meta.get("domain")
        company_name = meta.get("company")

        if comp_domain and comp_domain not in seen_domains:
            competitors.append({
                "domain": comp_domain,
                "company": company_name,
                "relevance_score": r.get("distance")
            })
            seen_domains.add(comp_domain)

    return competitors


# ============================================================================
# RAG & Database Query Tools
# ============================================================================

def market_search(query: str, n_results: int = 5) -> Dict[str, List[Dict]]:
    """
    Basic semantic search across raw_pages, products, and companies collections.

    Args:
        query: Natural language query
        n_results: Number of results to return (1-100)

    Returns:
        Dict with 'results' key containing list of matching documents
    """
    if not query or not query.strip():
        return {"results": [], "error": "Query cannot be empty"}

    n = max(1, min(int(n_results), 100))
    results = query_rag(query, top_k=n)
    return {"results": results}


def filter_search(query: str, key: str, value: str, n_results: int = 5) -> Dict[str, List[Dict]]:
    """
    Semantic search with a metadata filter.

    Args:
        query: Natural language query
        key: Metadata key to filter on (domain, brand, category, company)
        value: Value to match for the filter key
        n_results: Number of results to return (1-100)

    Returns:
        Dict with 'results' key containing filtered matching documents
    """
    if not query or not query.strip():
        return {"results": [], "error": "Query cannot be empty"}

    valid_keys = ["domain", "brand", "category", "company"]
    if key not in valid_keys:
        return {"results": [], "error": f"Invalid filter key '{key}'. Must be one of: {', '.join(valid_keys)}"}

    n = max(1, min(int(n_results), 100))
    results = query_rag(query, filters={key: value}, top_k=n)
    return {"results": results}


def get_domains() -> Dict[str, List[str]]:
    """
    List distinct domains available.
    Prefers embedded tracker, falls back to extracted data or ChromaDB.

    Returns:
        Dict with 'domains' key containing list of domain names
    """
    domains: List[str] = []

    # Try embedded tracker file first
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

    # Fall back to extracted data directory
    if not domains and EXTRACTED_DIR.exists():
        try:
            domains = sorted([p.name for p in EXTRACTED_DIR.iterdir() if p.is_dir()])
        except Exception:
            pass

    # Last resort: query ChromaDB
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


def get_contacts() -> Dict[str, List[Dict]]:
    """
    Return structured contacts and related profile fields per domain.

    Returns:
        Dict with 'contacts' key containing list of contact info per domain
    """
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


def get_stats() -> Dict[str, object]:
    """
    Return counts per collection, domain count, and embedded date range.

    Returns:
        Dict with collection counts, total domains, and embedding date range
    """
    stats: Dict[str, object] = {
        "collections": {},
        "domains": 0,
        "embedded_range": {"min": None, "max": None}
    }

    # Get collection counts from ChromaDB
    try:
        client = _get_chroma_client()
        for coll_name in ["raw_pages", "products", "companies"]:
            try:
                coll = client.get_collection(coll_name)
                stats["collections"][coll_name] = coll.count()
            except Exception:
                stats["collections"][coll_name] = 0
    except Exception:
        stats["collections"] = {"raw_pages": 0, "products": 0, "companies": 0}

    # Get domain count and date range from embedded tracker
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
                        except Exception:
                            pass
        except Exception:
            pass

    # Fall back to extracted directory if no embedded tracker
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


def get_recent_crawls(limit: int = 10) -> Dict[str, List[Dict]]:
    """
    Show last crawl activity from crawl_state files.

    Args:
        limit: Maximum number of recent crawls to return (1-100)

    Returns:
        Dict with 'recent' key containing list of recent crawl info
    """
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
            except Exception:
                pass

            entries.append({
                "domain": domain,
                "timestamp": ts,
                "sample_urls_tail": urls[-5:]
            })
    except Exception:
        pass

    return {"recent": entries}
