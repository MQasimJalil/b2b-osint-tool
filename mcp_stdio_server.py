import logging
from typing import Dict, List

from fastmcp import FastMCP

# Import all tools from agent_tools (single source of truth)
from pipeline.agent_tools import (
    # Domain-specific research tools
    get_company_profile,
    get_smykm_notes,
    get_product_catalog,
    analyze_pricing_strategy,
    find_competitors,
    # RAG & database query tools
    market_search,
    filter_search,
    get_domains,
    get_contacts,
    get_stats,
    get_recent_crawls
)

# Architecture Note:
# - pipeline.agent_tools contains ALL unwrapped functions (single source of truth)
# - This MCP server wraps them with @app.tool() for MCP clients
# - gemini_agent.py imports the same plain functions from agent_tools
# - Both systems use identical underlying implementations

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastMCP("b2b-osint-mcp-stdio")


# ============================================================================
# RAG & Database Query Tools
# ============================================================================

@app.tool()
def mcp_market_search(query: str, n_results: int = 5) -> Dict[str, List[Dict]]:
    """Basic semantic search across raw_pages, products, and companies collections."""
    return market_search(query, n_results)


@app.tool()
def mcp_filter_search(query: str, key: str, value: str, n_results: int = 5) -> Dict[str, List[Dict]]:
    """Semantic search with a metadata filter (domain, brand, category, company)."""
    return filter_search(query, key, value, n_results)


@app.tool()
def mcp_get_domains() -> Dict[str, List[str]]:
    """List distinct domains available (prefers embedded tracker, falls back to extracted data)."""
    return get_domains()


@app.tool()
def mcp_get_contacts() -> Dict[str, List[Dict]]:
    """Return structured contacts and related profile fields per domain."""
    return get_contacts()


@app.tool()
def mcp_get_stats() -> Dict[str, object]:
    """Return counts per collection, domain count, and embedded date range."""
    return get_stats()


@app.tool()
def mcp_get_recent_crawls(limit: int = 10) -> Dict[str, List[Dict]]:
    """Show last crawl activity from crawl_state files (timestamp + sample of URLs)."""
    return get_recent_crawls(limit)


# ============================================================================
# Domain-Specific Research Tools
# ============================================================================

@app.tool()
def mcp_get_company_profile(domain: str) -> Dict:
    """
    Retrieve structured company profile for a specific domain.
    Returns company name, description, SMYKM notes, contacts, and social media.
    """
    return get_company_profile(domain)


@app.tool()
def mcp_get_smykm_notes(domain: str) -> Dict:
    """
    Retrieve SMYKM (So Much You Didn't Know About Me) notes for a specific domain.
    Returns key insights about the company's unique value proposition, culture, and differentiators.
    These notes are critical for writing highly personalized outreach emails.
    """
    return get_smykm_notes(domain)


@app.tool()
def mcp_get_product_catalog(domain: str) -> List[Dict]:
    """
    Retrieve full product catalog for a specific domain.
    Returns list of products with brand, name, price, category, specs, and reviews.
    """
    return get_product_catalog(domain)


@app.tool()
def mcp_analyze_pricing_strategy(domain: str) -> Dict:
    """
    Analyze pricing strategy for a domain based on extracted products.
    Returns average price, min/max, price range, and product count.
    """
    return analyze_pricing_strategy(domain)


@app.tool()
def mcp_find_competitors(domain: str, industry: str = "goalkeeper gloves") -> List[Dict]:
    """
    Find potential competitors using RAG semantic search.
    Searches for similar companies in the specified industry.
    """
    return find_competitors(domain, industry)


if __name__ == "__main__":
    # Start stdio MCP server
    app.run()


