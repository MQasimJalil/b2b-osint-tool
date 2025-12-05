"""
Search engine integrations for company discovery.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse, quote_plus
import httpx
import logging
from bs4 import BeautifulSoup
import asyncio

logger = logging.getLogger(__name__)


class SearchEngine(ABC):
    """Base class for search engines."""

    def __init__(self, proxy_manager: Optional[Any] = None):
        self.proxy_manager = proxy_manager

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 100,
        region: str = "US"
    ) -> List[Dict[str, str]]:
        """
        Search for domains matching the query.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            region: Region/country code for search

        Returns:
            List of dicts containing 'domain', 'url', 'title', 'snippet'
        """
        pass

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain.lower()
        except Exception as e:
            logger.error(f"Error extracting domain from {url}: {e}")
            return ""

    async def _get_proxy(self) -> Optional[str]:
        """Get a proxy from the proxy manager if available."""
        if self.proxy_manager:
            return await self.proxy_manager.get_proxy()
        return None


class GoogleSearchEngine(SearchEngine):
    """Google search implementation using Custom Search API or scraping."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        search_engine_id: Optional[str] = None,
        proxy_manager: Optional[Any] = None,
        use_api: bool = True
    ):
        super().__init__(proxy_manager)
        self.api_key = api_key
        self.search_engine_id = search_engine_id
        self.use_api = use_api and api_key and search_engine_id

    async def search(
        self,
        query: str,
        max_results: int = 100,
        region: str = "US"
    ) -> List[Dict[str, str]]:
        """Search Google for domains."""
        if self.use_api:
            return await self._search_api(query, max_results, region)
        else:
            return await self._search_scrape(query, max_results, region)

    async def _search_api(
        self,
        query: str,
        max_results: int,
        region: str
    ) -> List[Dict[str, str]]:
        """Search using Google Custom Search API."""
        results = []
        num_pages = (max_results + 9) // 10  # API returns 10 results per page

        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(num_pages):
                start_index = page * 10 + 1

                try:
                    url = "https://www.googleapis.com/customsearch/v1"
                    params = {
                        "key": self.api_key,
                        "cx": self.search_engine_id,
                        "q": query,
                        "start": start_index,
                        "gl": region.lower(),
                        "num": min(10, max_results - len(results))
                    }

                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    for item in data.get("items", []):
                        domain = self._extract_domain(item["link"])
                        if domain:
                            results.append({
                                "domain": domain,
                                "url": item["link"],
                                "title": item.get("title", ""),
                                "snippet": item.get("snippet", ""),
                                "source": "google"
                            })

                    # Check if we have more results
                    if "queries" not in data or "nextPage" not in data["queries"]:
                        break

                except httpx.HTTPStatusError as e:
                    logger.error(f"Google API error: {e}")
                    if e.response.status_code == 429:
                        logger.warning("Google API rate limit reached")
                        break
                except Exception as e:
                    logger.error(f"Error searching Google API: {e}")
                    break

                # Respect rate limits
                await asyncio.sleep(0.5)

        return results[:max_results]

    async def _search_scrape(
        self,
        query: str,
        max_results: int,
        region: str
    ) -> List[Dict[str, str]]:
        """Search by scraping Google search results (fallback)."""
        results = []
        num_pages = (max_results + 9) // 10

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # Get proxy if available
        proxy = await self._get_proxy()

        # Create client with proxy if available
        client_kwargs = {"timeout": 30.0, "follow_redirects": True}
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            for page in range(num_pages):
                start_index = page * 10

                try:
                    url = f"https://www.google.com/search"
                    params = {
                        "q": query,
                        "start": start_index,
                        "gl": region.lower(),
                        "num": 10
                    }

                    response = await client.get(
                        url,
                        params=params,
                        headers=headers
                    )
                    response.raise_for_status()

                    # Parse results
                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Try multiple selectors as Google frequently changes its HTML structure
                    search_results = soup.select('div.g')
                    if not search_results:
                        search_results = soup.select('div[data-sokoban-container]')
                    if not search_results:
                        # Fallback: find all divs with h3 tags (common pattern)
                        search_results = [div for div in soup.find_all('div') if div.find('h3')]

                    for result in search_results:
                        try:
                            # Find link - try multiple approaches
                            link_elem = result.select_one('a')
                            if not link_elem:
                                link_elem = result.find('a', href=True)

                            if not link_elem or 'href' not in link_elem.attrs:
                                continue

                            link = link_elem['href']

                            # Skip Google internal links
                            if link.startswith('/search') or link.startswith('#') or 'google.com' in link:
                                continue

                            domain = self._extract_domain(link)
                            if not domain:
                                continue

                            # Extract title
                            title_elem = result.select_one('h3')
                            if not title_elem:
                                title_elem = result.find('h3')
                            title = title_elem.get_text(strip=True) if title_elem else ""

                            # Extract snippet - try multiple selectors
                            snippet_elem = result.select_one('div.VwiC3b')
                            if not snippet_elem:
                                snippet_elem = result.select_one('div.IsZvec')
                            if not snippet_elem:
                                snippet_elem = result.select_one('span.aCOpRe')
                            if not snippet_elem:
                                # Find any div with text content that's not the title
                                snippet_elem = result.find('div', text=True)

                            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                            results.append({
                                "domain": domain,
                                "url": link,
                                "title": title,
                                "snippet": snippet,
                                "source": "google"
                            })

                        except Exception as e:
                            logger.error(f"Error parsing search result: {e}")
                            continue

                except httpx.HTTPStatusError as e:
                    logger.error(f"Google scraping error: {e}")
                    if e.response.status_code == 429:
                        logger.warning("Google rate limit reached")
                        break
                except Exception as e:
                    logger.error(f"Error scraping Google: {e}")
                    break

                # Respect rate limits
                await asyncio.sleep(2)

        return results[:max_results]


class BingSearchEngine(SearchEngine):
    """Bing search implementation using Bing Search API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        proxy_manager: Optional[Any] = None
    ):
        super().__init__(proxy_manager)
        self.api_key = api_key

    async def search(
        self,
        query: str,
        max_results: int = 100,
        region: str = "US"
    ) -> List[Dict[str, str]]:
        """Search Bing for domains."""
        if self.api_key:
            return await self._search_api(query, max_results, region)
        else:
            return await self._search_scrape(query, max_results, region)

    async def _search_api(
        self,
        query: str,
        max_results: int,
        region: str
    ) -> List[Dict[str, str]]:
        """Search using Bing Search API."""
        results = []
        num_pages = (max_results + 49) // 50  # API can return up to 50 results per page

        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(num_pages):
                offset = page * 50

                try:
                    url = "https://api.bing.microsoft.com/v7.0/search"
                    params = {
                        "q": query,
                        "count": min(50, max_results - len(results)),
                        "offset": offset,
                        "mkt": f"{region.lower()}-{region}",
                        "responseFilter": "Webpages"
                    }

                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()

                    for item in data.get("webPages", {}).get("value", []):
                        domain = self._extract_domain(item["url"])
                        if domain:
                            results.append({
                                "domain": domain,
                                "url": item["url"],
                                "title": item.get("name", ""),
                                "snippet": item.get("snippet", ""),
                                "source": "bing"
                            })

                    # Check if we have more results
                    if len(results) >= data.get("webPages", {}).get("totalEstimatedMatches", 0):
                        break

                except httpx.HTTPStatusError as e:
                    logger.error(f"Bing API error: {e}")
                    break
                except Exception as e:
                    logger.error(f"Error searching Bing API: {e}")
                    break

                # Respect rate limits
                await asyncio.sleep(0.5)

        return results[:max_results]

    async def _search_scrape(
        self,
        query: str,
        max_results: int,
        region: str
    ) -> List[Dict[str, str]]:
        """Search by scraping Bing search results (fallback)."""
        results = []
        num_pages = (max_results + 9) // 10

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # Get proxy if available
        proxy = await self._get_proxy()

        # Create client with proxy if available
        client_kwargs = {"timeout": 30.0, "follow_redirects": True}
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            for page in range(num_pages):
                first_index = page * 10 + 1

                try:
                    url = "https://www.bing.com/search"
                    params = {
                        "q": query,
                        "first": first_index,
                        "count": 10
                    }

                    response = await client.get(
                        url,
                        params=params,
                        headers=headers
                    )
                    response.raise_for_status()

                    # Parse results
                    soup = BeautifulSoup(response.text, 'html.parser')
                    search_results = soup.select('li.b_algo')

                    for result in search_results:
                        try:
                            link_elem = result.select_one('h2 a')
                            if not link_elem or 'href' not in link_elem.attrs:
                                continue

                            link = link_elem['href']
                            domain = self._extract_domain(link)
                            title = link_elem.get_text()

                            snippet_elem = result.select_one('p')
                            snippet = snippet_elem.get_text() if snippet_elem else ""

                            if domain:
                                results.append({
                                    "domain": domain,
                                    "url": link,
                                    "title": title,
                                    "snippet": snippet,
                                    "source": "bing"
                                })

                        except Exception as e:
                            logger.error(f"Error parsing search result: {e}")
                            continue

                except httpx.HTTPStatusError as e:
                    logger.error(f"Bing scraping error: {e}")
                    break
                except Exception as e:
                    logger.error(f"Error scraping Bing: {e}")
                    break

                # Respect rate limits
                await asyncio.sleep(2)

        return results[:max_results]


def get_search_engine(
    engine: str,
    google_api_key: Optional[str] = None,
    google_search_engine_id: Optional[str] = None,
    bing_api_key: Optional[str] = None,
    proxy_manager: Optional[Any] = None
) -> SearchEngine:
    """
    Factory function to get a search engine instance.

    Args:
        engine: Engine name ('google' or 'bing')
        google_api_key: Google Custom Search API key
        google_search_engine_id: Google Custom Search Engine ID
        bing_api_key: Bing Search API key
        proxy_manager: Optional proxy manager instance

    Returns:
        SearchEngine instance
    """
    if engine.lower() == "google":
        return GoogleSearchEngine(
            api_key=google_api_key,
            search_engine_id=google_search_engine_id,
            proxy_manager=proxy_manager
        )
    elif engine.lower() == "bing":
        return BingSearchEngine(
            api_key=bing_api_key,
            proxy_manager=proxy_manager
        )
    else:
        raise ValueError(f"Unsupported search engine: {engine}")
