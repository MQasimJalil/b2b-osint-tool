"""
Pydantic schemas for discovery operations.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class DiscoveryJobConfig(BaseModel):
    """Configuration for discovery jobs."""
    keywords: List[str] = Field(..., description="Keywords to search for")
    search_engines: List[str] = Field(default=["google"], description="Search engines to use")
    region: str = Field(default="US", description="Region for search results")
    max_results_per_engine: int = Field(default=50, description="Max results per engine")
    proxy_mode: str = Field(default="none", description="Proxy mode")
    proxies: Optional[List[str]] = Field(default=None, description="Proxy URLs")
    google_api_key: Optional[str] = Field(default=None, description="Google API key")
    google_search_engine_id: Optional[str] = Field(default=None, description="Google search engine ID")
    bing_api_key: Optional[str] = Field(default=None, description="Bing API key")
