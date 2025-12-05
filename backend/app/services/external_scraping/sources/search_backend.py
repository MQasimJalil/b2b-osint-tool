"""
Unified Search Backend with Fallback Chain

Provides a resilient search system that automatically falls back
through multiple search engines when one fails or is rate limited.

Search options:
1. Google Custom Search API (RECOMMENDED - 100 queries/day free, then $5/1000)
2. DuckDuckGo (free, no API key, rate limited)
3. Bing Search API (free tier: 1,000/month, requires API key)
4. googlesearch-python (free, scrapes Google, may be blocked)

Usage:
    # With Google Custom Search API (recommended)
    backend = SearchBackend(
        google_api_key='your-key',
        google_search_engine_id='your-cx'
    )

    # With fallback chain
    backend = SearchBackend(bing_api_key='your-key')  # Optional

    results = backend.search('site:linkedin.com company name')
"""

import logging
import time
import os
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Standardized search result."""
    title: str
    url: str
    snippet: str
    source: str  # 'duckduckgo', 'bing', 'google'


class SearchBackend:
    """
    Unified search backend with automatic fallback.

    Tries search engines in order until one succeeds:
    1. DuckDuckGo
    2. Bing (if API key provided)
    3. Google (googlesearch-python)
    """

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        google_search_engine_id: Optional[str] = None,
        bing_api_key: Optional[str] = None,
        retry_delay: float = 2.0,
        max_retries: int = 2
    ):
        """
        Initialize search backend.

        Args:
            google_api_key: Google Custom Search API key (RECOMMENDED)
            google_search_engine_id: Google Custom Search Engine ID (cx)
            bing_api_key: Optional Bing API key (from Azure)
            retry_delay: Delay between retries (seconds)
            max_retries: Max retries per engine
        """
        self.google_api_key = google_api_key or os.getenv('GOOGLE_SEARCH_KEY')
        self.google_cx = google_search_engine_id or os.getenv('GOOGLE_SEARCH_ENGINE_ID')
        self.bing_api_key = bing_api_key or os.getenv('BING_SEARCH_API_KEY')
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self._last_search_time = {}

        # Track which engines are available
        self._engines_available = {
            'google_custom': self._check_google_custom(),
            'duckduckgo': self._check_duckduckgo(),
            'bing': self._check_bing(),
            'google_scrape': self._check_google_scrape()
        }

        logger.info(f"Search engines available: {[k for k, v in self._engines_available.items() if v]}")

        if self.google_api_key and self.google_cx:
            logger.info("Google Custom Search API configured (RECOMMENDED)")
        else:
            logger.info("Google API key not found. Set GOOGLE_SEARCH_KEY and GOOGLE_SEARCH_ENGINE_ID env vars to enable.")

        if self.bing_api_key:
            logger.info("Bing API key configured")
        else:
            logger.info("Bing API key not found. Set BING_SEARCH_API_KEY env var to enable.")

    def _check_google_custom(self) -> bool:
        """Check if Google Custom Search API is available."""
        if not (self.google_api_key and self.google_cx):
            return False
        try:
            import requests
            return True
        except ImportError:
            logger.warning("requests not installed (needed for Google API)")
            return False

    def _check_duckduckgo(self) -> bool:
        """Check if DuckDuckGo is available."""
        try:
            from duckduckgo_search import DDGS
            return True
        except ImportError:
            logger.warning("duckduckgo_search not installed")
            return False

    def _check_bing(self) -> bool:
        """Check if Bing API is available."""
        if not self.bing_api_key:
            return False
        try:
            import requests
            return True  # requests should already be installed
        except ImportError:
            logger.warning("requests not installed (needed for Bing)")
            return False

    def _check_google_scrape(self) -> bool:
        """Check if googlesearch-python is available."""
        try:
            import googlesearch
            return True
        except ImportError:
            logger.info("googlesearch-python not installed (optional fallback)")
            return False

    def search(
        self,
        query: str,
        max_results: int = 10,
        preferred_engine: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Search with automatic fallback.

        Args:
            query: Search query
            max_results: Maximum results to return
            preferred_engine: Try this engine first (optional)

        Returns:
            List of SearchResult objects
        """
        # Determine engine order
        engine_order = self._get_engine_order(preferred_engine)

        last_error = None

        for engine in engine_order:
            if not self._engines_available.get(engine, False):
                continue

            try:
                logger.debug(f"Trying search engine: {engine}")
                results = self._search_with_engine(engine, query, max_results)

                if results:
                    logger.info(f"Search successful with {engine}: {len(results)} results")
                    return results
                else:
                    logger.debug(f"{engine} returned no results")

            except Exception as e:
                last_error = e
                logger.warning(f"{engine} search failed: {e}")

                # Check if it's a rate limit error
                if self._is_rate_limit_error(e):
                    logger.warning(f"{engine} rate limited, trying next engine...")
                    continue
                else:
                    # Non-rate-limit error, still try next engine
                    continue

        # All engines failed
        error_msg = f"All search engines failed. Last error: {last_error}"
        logger.error(error_msg)
        return []

    def _get_engine_order(self, preferred: Optional[str] = None) -> List[str]:
        """
        Get search engine fallback order.

        Priority:
        1. Google Custom Search API (if configured) - BEST
        2. Bing Search API (if configured)
        3. googlesearch-python scraper (last resort)

        Note: DuckDuckGo is excluded due to aggressive rate limiting
        """
        # If Google Custom Search API is available, use it exclusively
        if self._engines_available.get('google_custom', False):
            return ['google_custom']

        # Otherwise use fallback chain without DuckDuckGo (too unreliable)
        default_order = ['bing', 'google_scrape']

        if preferred and preferred in default_order:
            # Move preferred to front
            order = [preferred] + [e for e in default_order if e != preferred]
            return order

        return default_order

    def _search_with_engine(
        self,
        engine: str,
        query: str,
        max_results: int
    ) -> List[SearchResult]:
        """Execute search with specific engine."""
        # Rate limiting
        self._apply_rate_limit(engine)

        if engine == 'google_custom':
            return self._search_google_custom(query, max_results)
        elif engine == 'duckduckgo':
            return self._search_duckduckgo(query, max_results)
        elif engine == 'bing':
            return self._search_bing(query, max_results)
        elif engine == 'google_scrape':
            return self._search_google_scrape(query, max_results)
        else:
            raise ValueError(f"Unknown engine: {engine}")

    def _apply_rate_limit(self, engine: str):
        """Apply rate limiting between searches."""
        last_time = self._last_search_time.get(engine, 0)
        elapsed = time.time() - last_time

        if elapsed < self.retry_delay:
            sleep_time = self.retry_delay - elapsed
            logger.debug(f"Rate limiting {engine}: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)

        self._last_search_time[engine] = time.time()

    def _search_duckduckgo(self, query: str, max_results: int) -> List[SearchResult]:
        """Search using DuckDuckGo."""
        from duckduckgo_search import DDGS

        results = []

        for attempt in range(self.max_retries):
            try:
                with DDGS() as ddgs:
                    search_results = list(ddgs.text(query, max_results=max_results))

                    for result in search_results:
                        results.append(SearchResult(
                            title=result.get('title', ''),
                            url=result.get('href', ''),
                            snippet=result.get('body', ''),
                            source='duckduckgo'
                        ))

                    return results

            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.debug(f"DuckDuckGo retry in {wait_time:.1f}s")
                    time.sleep(wait_time)
                else:
                    raise

        return results

    def _search_bing(self, query: str, max_results: int) -> List[SearchResult]:
        """Search using Bing API."""
        if not self.bing_api_key:
            raise ValueError("Bing API key not configured")

        import requests

        endpoint = "https://api.bing.microsoft.com/v7.0/search"

        headers = {
            'Ocp-Apim-Subscription-Key': self.bing_api_key
        }

        params = {
            'q': query,
            'count': max_results,
            'textDecorations': False,
            'textFormat': 'Raw'
        }

        response = requests.get(
            endpoint,
            headers=headers,
            params=params,
            timeout=10
        )

        response.raise_for_status()
        data = response.json()

        results = []

        # Parse Bing results
        web_pages = data.get('webPages', {}).get('value', [])
        for page in web_pages:
            results.append(SearchResult(
                title=page.get('name', ''),
                url=page.get('url', ''),
                snippet=page.get('snippet', ''),
                source='bing'
            ))

        return results

    def _search_google_custom(self, query: str, max_results: int) -> List[SearchResult]:
        """Search using Google Custom Search API."""
        import requests

        endpoint = "https://www.googleapis.com/customsearch/v1"

        params = {
            'key': self.google_api_key,
            'cx': self.google_cx,
            'q': query,
            'num': min(max_results, 10)  # Google API max is 10 per request
        }

        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []

        # Parse Google Custom Search results
        items = data.get('items', [])
        for item in items:
            results.append(SearchResult(
                title=item.get('title', ''),
                url=item.get('link', ''),
                snippet=item.get('snippet', ''),
                source='google_custom'
            ))

        return results

    def _search_google_scrape(self, query: str, max_results: int) -> List[SearchResult]:
        """Search using googlesearch-python (scraping)."""
        from googlesearch import search

        results = []

        # googlesearch returns just URLs, need to fetch titles/snippets
        try:
            urls = list(search(query, num_results=max_results, sleep_interval=2))

            for url in urls:
                results.append(SearchResult(
                    title='',  # googlesearch doesn't provide titles
                    url=url,
                    snippet='',
                    source='google_scrape'
                ))

        except Exception as e:
            logger.warning(f"Google scrape error: {e}")
            raise

        return results

    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if error is due to rate limiting."""
        error_str = str(error).lower()

        rate_limit_indicators = [
            'ratelimit',
            '202',
            '429',
            'too many requests',
            'rate limit',
            'quota exceeded'
        ]

        return any(indicator in error_str for indicator in rate_limit_indicators)


# Convenience function
def search(query: str, max_results: int = 10) -> List[SearchResult]:
    """
    Quick search function with fallback.

    Args:
        query: Search query
        max_results: Max results

    Returns:
        List of SearchResult objects
    """
    backend = SearchBackend()
    return backend.search(query, max_results)
