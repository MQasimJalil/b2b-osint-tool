import os
import json
from typing import List, Dict, Optional, Any
from pymongo import MongoClient

# Import RAG functions (Synchronous)
try:
    from app.services.rag.rag import query_rag
except ImportError:
    # Fallback if path issues
    from backend.app.services.rag.rag import query_rag

# Global client cache to avoid reconnection overhead per call if reused in same process
_mongo_client = None

def _get_db():
    """Get synchronous MongoDB database connection."""
    global _mongo_client
    if _mongo_client is None:
        mongo_uri = os.getenv("DATABASE_URL") or os.getenv("MONGODB_URI", "mongodb://mongodb:27017/b2b_osint")
        # Parse database name
        if "/" in mongo_uri and mongo_uri.split("/")[-1]:
            _mongo_client = MongoClient(mongo_uri.rsplit("/", 1)[0])
            # db_name handled below or in URI? MongoClient doesn't pick DB from URI path usually unless get_database() used
            # But standard is client.get_database()
        else:
            _mongo_client = MongoClient(mongo_uri)
    
    # Determine DB name
    mongo_uri = os.getenv("DATABASE_URL") or "mongodb://mongodb:27017/b2b_osint"
    db_name = "b2b_osint"
    if "/" in mongo_uri and mongo_uri.split("/")[-1]:
        possible_name = mongo_uri.split("/")[-1].split("?")[0]
        if possible_name:
            db_name = possible_name
            
    return _mongo_client[db_name]

# ============================================================================
# Core Company Data Tools (Synchronous)
# ============================================================================

def get_company_profile(domain: str) -> Dict[str, Any]:
    """
    Retrieve structured company profile for a specific domain.

    Args:
        domain: The domain name to retrieve

    Returns:
        Dictionary with company profile or error message
    """
    try:
        db = _get_db()
        company = db.companies.find_one({"domain": domain})

        if not company:
            return {"error": f"Company profile not found for {domain}"}

        # Format contacts
        emails = []
        if "contacts" in company:
            emails = [c.get("value") for c in company["contacts"] if c.get("type") == "email"]

        return {
            "domain": company.get("domain"),
            "company": company.get("company_name"),
            "email": emails,
            "description": company.get("description"),
            "founded": str(company.get("founded")) if company.get("founded") else None, # If available
            "location": company.get("location") # If available
        }

    except Exception as e:
        return {"error": f"Error reading company data: {str(e)}"}


def get_smykm_notes(domain: str) -> Dict[str, Any]:
    """
    Retrieve SMYKM (Show me you know me) notes for a specific domain.
    These are key insights about the company's unique value proposition, culture, and differentiators.

    Args:
        domain: The domain name

    Returns:
        Dict with notes and description
    """
    try:
        db = _get_db()
        company = db.companies.find_one({"domain": domain})

        if not company:
            return {
                "error": f"Company profile not found for {domain}",
                "domain": domain,
                "smykm_notes": []
            }

        return {
            "domain": company.get("domain"),
            "company": company.get("company_name"),
            "description": company.get("description"),
            "smykm_notes": company.get("smykm_notes", [])
        }

    except Exception as e:
        return {
            "error": f"Error reading profile for {domain}: {str(e)}",
            "domain": domain,
            "smykm_notes": []
        }

def get_product_catalog(domain: str) -> List[Dict[str, Any]]:
    """
    Retrieve full product catalog for a specific domain.

    Args:
        domain: The domain name

    Returns:
        List of product dictionaries
    """
    try:
        db = _get_db()
        # Exclude _id field for cleaner output
        products = list(db.products.find(
            {"domain": domain}, 
            {
                "_id": 0,
                "brand": 1,
                "name": 1,
                "category": 1,
                "price": 1,
                "description": 1,
                "specs": 1,
                "reviews": 1,
                "url": 1,
                "image_url": 1,
                "product_id": 1
            }
        ))

        if not products:
            return []

        return products

    except Exception as e:
        return [{"error": f"Error reading product data: {str(e)}"}]

def analyze_pricing_strategy(domain: str) -> Dict[str, Any]:
    """
    Analyze pricing strategy for a domain based on extracted products.
    Returns average price, min/max, and price range distribution.
    """
    products = get_product_catalog(domain)
    if not products or (isinstance(products, list) and len(products) > 0 and "error" in products[0]):
        return {"error": "No products found to analyze."}
    
    prices = []
    for p in products:
        price_val = p.get("price")
        if not price_val:
            continue
            
        # Handle string prices like "$19.99" or "19.99 USD"
        price_str = str(price_val)
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

def find_competitors(domain: str, industry: str = "goalkeeper gloves") -> List[Dict[str, Any]]:
    """
    Find potential competitors using RAG semantic search.
    Searches for similar companies in the 'companies' collection.
    """
    query = f"competitors for {domain} in {industry} industry"

    # Query RAG 'companies' collection (Synchronous)
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
    List distinct domains available in the database.

    Returns:
        Dict with 'domains' key containing list of domain names
    """
    try:
        db = _get_db()
        domains = db.companies.distinct("domain")
        return {"domains": sorted(domains)}
    except Exception:
        return {"domains": []}


def get_contacts(domain: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    Return structured contacts and related profile fields per domain.

    Args:
        domain: Optional domain to filter by.

    Returns:
        Dict with 'contacts' key containing list of contact info
    """
    contacts: List[Dict] = []
    try:
        db = _get_db()
        query = {}
        if domain:
            query["domain"] = domain
            
        # Limit to 20 if no domain specified to avoid huge payloads
        limit = 0 if domain else 20
        
        cursor = db.companies.find(query, {
            "domain": 1, "company_name": 1, "contacts": 1, "social_media": 1
        }).limit(limit)

        for doc in cursor:
            # Format similar to legacy output for compatibility
            # Group contacts by type
            main_contacts = {"email": [], "phone": [], "address": []}
            if "contacts" in doc:
                for c in doc["contacts"]:
                    ctype = c.get("type")
                    if ctype in main_contacts:
                        main_contacts[ctype].append(c.get("value"))
            
            entry = {
                "domain": doc.get("domain"),
                "company": doc.get("company_name"),
                "main_contacts": main_contacts,
                "social": doc.get("social_media") or [],
            }
            contacts.append(entry)

    except Exception:
        pass

    return {"contacts": contacts}


def get_stats() -> Dict[str, object]:
    """
    Return counts per collection.

    Returns:
        Dict with collection counts
    """
    stats: Dict[str, object] = {
        "collections": {},
        "domains": 0
    }

    try:
        db = _get_db()
        stats["collections"]["companies"] = db.companies.count_documents({})
        stats["collections"]["products"] = db.products.count_documents({})
        stats["collections"]["raw_pages"] = db.crawled_pages.count_documents({})
        stats["domains"] = len(db.companies.distinct("domain"))
    except Exception:
        pass

    return stats


def get_recent_crawls(limit: int = 10) -> Dict[str, List[Dict]]:
    """
    Show last completed crawls.

    Args:
        limit: Maximum number of recent crawls to return (1-100)

    Returns:
        Dict with 'recent' key containing list of recent crawl info
    """
    entries: List[Dict] = []
    try:
        db = _get_db()
        cursor = db.companies.find(
            {"crawl_status": "completed", "crawled_at": {"$ne": None}},
            {"domain": 1, "crawled_at": 1, "crawled_pages": 1}
        ).sort("crawled_at", -1).limit(max(1, min(int(limit), 100)))

        for doc in cursor:
            entries.append({
                "domain": doc.get("domain"),
                "pages": doc.get("crawled_pages", 0)
            })
    except Exception:
        pass

    return {"recent": entries}