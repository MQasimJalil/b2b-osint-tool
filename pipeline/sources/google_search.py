"""
Google Search Contact Discovery

Uses intelligent search queries to find contact information
for companies that don't have it on their websites.

Queries:
- "[company] phone number"
- "[company] whatsapp"
- "[company] contact"
- "[company] linkedin"

Uses fallback search (DuckDuckGo -> Bing -> Google) for resilience.
"""

import logging
import time
from typing import List, Dict, Optional

from pipeline.contact_patterns import (
    extract_phones,
    extract_whatsapp,
    extract_linkedin,
    ContactMatch
)
from pipeline.sources.search_backend import SearchBackend

logger = logging.getLogger(__name__)


class GoogleContactSearch:
    """Uses search engines to find contact information."""

    def __init__(
        self,
        max_results: int = 5,
        google_api_key: Optional[str] = None,
        google_cx: Optional[str] = None,
        bing_api_key: Optional[str] = None
    ):
        """
        Initialize search.

        Args:
            max_results: Max search results per query
            google_api_key: Google Custom Search API key (RECOMMENDED)
            google_cx: Google Custom Search Engine ID
            bing_api_key: Optional Bing API key (for fallback)
        """
        self.max_results = max_results
        self.search_backend = SearchBackend(
            google_api_key=google_api_key,
            google_search_engine_id=google_cx,
            bing_api_key=bing_api_key
        )

    def search_contacts(
        self,
        domain: str,
        company_name: str = None,
        mode: str = 'lenient'
    ) -> Dict[str, List[ContactMatch]]:
        """
        Search for contacts using intelligent queries.

        Args:
            domain: Company domain
            company_name: Company name (optional, for better queries)
            mode: 'lenient' (basic queries) or 'aggressive' (more queries)

        Returns:
            Dict with keys: phones, whatsapp, linkedin
        """
        logger.info(f"[{domain}] Starting search in {mode} mode")

        results = {
            'phones': [],
            'whatsapp': [],
            'linkedin': []
        }

        # Use company name if available, otherwise use domain
        query_term = company_name or domain.split('.')[0]

        # Build queries based on mode
        queries = self._build_queries(query_term, domain, mode)

        # Execute searches
        for query_type, query in queries:
            try:
                search_results = self._execute_search(query)
                query_matches = self._extract_from_search_results(
                    search_results,
                    query_type
                )
                self._merge_results(results, query_matches)

                # Rate limiting
                time.sleep(2)

            except Exception as e:
                logger.warning(f"[{domain}] Search failed for '{query}': {e}")
                continue

        logger.info(
            f"[{domain}] Search found: {len(results['phones'])} phones, "
            f"{len(results['whatsapp'])} WhatsApp, "
            f"{len(results['linkedin'])} LinkedIn"
        )

        return results

    def _build_queries(
        self,
        company_name: str,
        domain: str,
        mode: str
    ) -> List[tuple]:
        """
        Build search queries based on mode.

        Args:
            company_name: Company name or domain stem
            domain: Full domain
            mode: Search mode

        Returns:
            List of (query_type, query_string) tuples
        """
        queries = []

        # Basic queries (lenient mode)
        queries.extend([
            ('phone', f'"{company_name}" phone number contact'),
            ('whatsapp', f'"{company_name}" whatsapp'),
            ('linkedin', f'"{company_name}" linkedin company'),
        ])

        if mode == 'aggressive':
            # Additional queries for aggressive mode
            queries.extend([
                ('phone', f'site:{domain} phone'),
                ('phone', f'site:{domain} tel'),
                ('whatsapp', f'site:{domain} wa.me'),
                ('whatsapp', f'"{company_name}" whatsapp business'),
                ('linkedin', f'site:linkedin.com/company {company_name}'),
                ('linkedin', f'site:linkedin.com/in {company_name}'),
            ])

        return queries

    def _execute_search(self, query: str) -> List[Dict]:
        """
        Execute a search query using search backend with fallback.

        Args:
            query: Search query

        Returns:
            List of search result dicts
        """
        try:
            search_results = self.search_backend.search(query, max_results=self.max_results)

            # Convert SearchResult objects to dict format
            results = []
            for result in search_results:
                results.append({
                    'title': result.title,
                    'href': result.url,
                    'body': result.snippet
                })

            return results

        except Exception as e:
            logger.debug(f"Search error for '{query}': {e}")
            return []

    def _extract_from_search_results(
        self,
        search_results: List[Dict],
        query_type: str
    ) -> Dict[str, List[ContactMatch]]:
        """
        Extract contacts from search results.

        Args:
            search_results: Search result dicts
            query_type: Type of query (phone, whatsapp, linkedin)

        Returns:
            Dict with extracted contacts
        """
        results = {
            'phones': [],
            'whatsapp': [],
            'linkedin': []
        }

        for result in search_results:
            # Combine title and snippet
            text = f"{result.get('title', '')} {result.get('body', '')}"
            url = result.get('href', '')

            if query_type == 'phone':
                # Extract phones
                phone_matches = extract_phones(text, context_chars=100)
                for match in phone_matches:
                    match.source = 'google_search'
                    match.confidence = 0.7  # Medium confidence for search results
                    results['phones'].append(match)

            elif query_type == 'whatsapp':
                # Extract WhatsApp
                whatsapp_matches = extract_whatsapp(text, html=url)
                for match in whatsapp_matches:
                    match.source = 'google_search'
                    match.confidence = 0.75
                    results['whatsapp'].append(match)

            elif query_type == 'linkedin':
                # Extract LinkedIn URLs
                if 'linkedin.com' in url:
                    # Found LinkedIn in URL - high confidence
                    results['linkedin'].append(ContactMatch(
                        value=url,
                        type='linkedin_company' if '/company/' in url else 'linkedin_individual',
                        confidence=0.85,
                        context=text[:100],
                        source='google_search'
                    ))
                else:
                    # Try to extract from text
                    linkedin_matches = extract_linkedin(text)
                    for match in linkedin_matches:
                        match.source = 'google_search'
                        match.confidence = 0.7
                        results['linkedin'].append(match)

        return results

    def _merge_results(
        self,
        target: Dict[str, List],
        source: Dict[str, List]
    ):
        """Merge source into target (in-place)."""
        for key in ['phones', 'whatsapp', 'linkedin']:
            if key in source:
                target[key].extend(source[key])


# Convenience function
def search_company_contacts(
    domain: str,
    company_name: str = None,
    mode: str = 'lenient'
) -> Dict:
    """
    Quick function to search for company contacts.

    Args:
        domain: Company domain
        company_name: Company name (optional)
        mode: Search mode

    Returns:
        Dict with contact results
    """
    searcher = GoogleContactSearch()
    return searcher.search_contacts(domain, company_name, mode)
