"""
LinkedIn Profile Discovery

Finds LinkedIn company pages and employee profiles.

Note: This uses public search and profile pages only.
Does not require LinkedIn API or authentication.

Uses fallback search (DuckDuckGo -> Bing -> Google) for resilience.
"""

import logging
import re
from typing import List, Dict, Optional

from pipeline.contact_patterns import ContactMatch
from pipeline.sources.search_backend import SearchBackend

logger = logging.getLogger(__name__)


class LinkedInDiscovery:
    """Discovers LinkedIn profiles for companies and employees."""

    def __init__(
        self,
        max_results: int = 10,
        google_api_key: Optional[str] = None,
        google_cx: Optional[str] = None,
        bing_api_key: Optional[str] = None
    ):
        """
        Initialize LinkedIn discovery.

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

    def discover_profiles(
        self,
        domain: str,
        company_name: str = None,
        mode: str = 'lenient'
    ) -> Dict[str, List[ContactMatch]]:
        """
        Discover LinkedIn profiles for a company with strict filtering.

        Args:
            domain: Company domain
            company_name: Company name (optional)
            mode: 'lenient' (company page only) or 'aggressive' (+ employees)

        Returns:
            Dict with keys: company_pages, employee_profiles
        """
        logger.info(f"[{domain}] Discovering LinkedIn profiles in {mode} mode")

        results = {
            'company_pages': [],
            'employee_profiles': []
        }

        query_term = company_name or domain.split('.')[0]
        domain_stem = domain.split('.')[0].lower()

        # 1. Find company page - strict filtering
        company_query = f'site:linkedin.com/company {query_term}'
        company_search_results = self._search_linkedin_with_context(company_query)

        for result in company_search_results:
            url = result['url']
            if '/company/' in url:
                # Strict verification: company name/domain must be in URL or context
                if self._verify_company_match(url, result['context'], query_term, domain_stem):
                    # Calculate confidence based on relevance
                    confidence = self._calculate_relevance_score(
                        url, result['context'], query_term, domain_stem
                    )

                    if confidence >= 0.7:  # Minimum threshold
                        results['company_pages'].append(ContactMatch(
                            value=url,
                            type='linkedin_company',
                            confidence=confidence,
                            context=result['context'][:100],
                            source='linkedin_search'
                        ))

        # 2. If aggressive mode, find employee profiles with strict filtering
        if mode == 'aggressive':
            # Search for employees
            employee_query = f'site:linkedin.com/in "{query_term}" (CEO OR founder OR director OR manager)'
            employee_search_results = self._search_linkedin_with_context(employee_query)

            filtered_employees = []
            for result in employee_search_results:
                url = result['url']
                if '/in/' in url:
                    # Strict verification: must mention company in title/snippet
                    if self._verify_employee_match(url, result['context'], query_term, domain_stem):
                        confidence = self._calculate_relevance_score(
                            url, result['context'], query_term, domain_stem
                        )

                        if confidence >= 0.6:  # Slightly lower threshold for individuals
                            name = self._extract_name_from_linkedin_url(url)
                            filtered_employees.append({
                                'url': url,
                                'name': name,
                                'confidence': confidence,
                                'context': result['context']
                            })

            # Sort by confidence and take top 3 (not 5)
            filtered_employees.sort(key=lambda x: x['confidence'], reverse=True)
            for employee in filtered_employees[:3]:
                results['employee_profiles'].append(ContactMatch(
                    value=employee['url'],
                    type='linkedin_individual',
                    confidence=employee['confidence'],
                    context=f"{employee['name']} - {employee['context'][:80]}" if employee['name'] else employee['context'][:100],
                    source='linkedin_search'
                ))

        logger.info(
            f"[{domain}] Found: {len(results['company_pages'])} company pages, "
            f"{len(results['employee_profiles'])} employee profiles"
        )

        return results

    def _search_linkedin_with_context(self, query: str) -> List[Dict[str, str]]:
        """
        Search for LinkedIn profiles with full context for filtering.

        Args:
            query: Search query

        Returns:
            List of dicts with url, title, context
        """
        results = []

        try:
            search_results = self.search_backend.search(query, max_results=self.max_results)

            for result in search_results:
                url = result.url
                if 'linkedin.com' in url:
                    # Clean URL (remove tracking params)
                    url = url.split('?')[0]

                    # Combine title and snippet for context
                    context = f"{result.title} {result.snippet}".lower()

                    results.append({
                        'url': url,
                        'title': result.title,
                        'context': context
                    })

        except Exception as e:
            logger.error(f"LinkedIn search failed: {e}")

        return results

    def _verify_company_match(
        self,
        url: str,
        context: str,
        company_name: str,
        domain_stem: str
    ) -> bool:
        """
        Verify that a LinkedIn company URL is actually for the target company.

        Args:
            url: LinkedIn URL
            context: Search result title + snippet
            company_name: Company name
            domain_stem: Domain without TLD

        Returns:
            True if verified match
        """
        url_lower = url.lower()
        context_lower = context.lower()
        company_lower = company_name.lower()
        domain_lower = domain_stem.lower()

        # Must have company name or domain in URL or context
        has_in_url = (company_lower in url_lower) or (domain_lower in url_lower)
        has_in_context = (company_lower in context_lower) or (domain_lower in context_lower)

        return has_in_url or has_in_context

    def _verify_employee_match(
        self,
        url: str,
        context: str,
        company_name: str,
        domain_stem: str
    ) -> bool:
        """
        Verify that a LinkedIn individual profile is actually related to the company.

        Args:
            url: LinkedIn URL
            context: Search result title + snippet
            company_name: Company name
            domain_stem: Domain without TLD

        Returns:
            True if verified match
        """
        context_lower = context.lower()
        company_lower = company_name.lower()
        domain_lower = domain_stem.lower()

        # Must explicitly mention company name or domain in the context
        # This is stricter than company pages
        has_company = company_lower in context_lower
        has_domain = domain_lower in context_lower

        # Additional check: look for "at [company]" or "[company] |" patterns
        at_company = f"at {company_lower}" in context_lower
        company_bar = f"{company_lower} |" in context_lower or f"| {company_lower}" in context_lower

        return has_company or has_domain or at_company or company_bar

    def _calculate_relevance_score(
        self,
        url: str,
        context: str,
        company_name: str,
        domain_stem: str
    ) -> float:
        """
        Calculate relevance score for a LinkedIn result.

        Args:
            url: LinkedIn URL
            context: Search result title + snippet
            company_name: Company name
            domain_stem: Domain without TLD

        Returns:
            Relevance score between 0 and 1
        """
        score = 0.5  # Base score

        url_lower = url.lower()
        context_lower = context.lower()
        company_lower = company_name.lower()
        domain_lower = domain_stem.lower()

        # URL contains company name or domain (+0.3)
        if company_lower in url_lower or domain_lower in url_lower:
            score += 0.3

        # Context contains company name (+0.2)
        if company_lower in context_lower:
            score += 0.2

        # Context contains domain (+0.15)
        if domain_lower in context_lower:
            score += 0.15

        # Exact match in URL (+0.2 bonus)
        url_slug = url.split('/')[-1].lower()
        if company_lower.replace(' ', '-') in url_slug or domain_lower in url_slug:
            score += 0.2

        # Cap at 1.0
        return min(score, 1.0)

    def _extract_name_from_linkedin_url(self, url: str) -> Optional[str]:
        """
        Extract person name from LinkedIn URL.

        Args:
            url: LinkedIn profile URL

        Returns:
            Extracted name or None
        """
        # LinkedIn URLs like: linkedin.com/in/john-doe-12345678
        match = re.search(r'/in/([\w\-]+)', url)
        if match:
            slug = match.group(1)
            # Remove trailing numbers
            slug = re.sub(r'-\d+$', '', slug)
            # Convert to readable name
            name = slug.replace('-', ' ').title()
            return name

        return None


# Convenience function
def discover_linkedin_profiles(
    domain: str,
    company_name: str = None,
    mode: str = 'lenient'
) -> Dict:
    """
    Quick function to discover LinkedIn profiles.

    Args:
        domain: Company domain
        company_name: Company name (optional)
        mode: Discovery mode

    Returns:
        Dict with LinkedIn results
    """
    discovery = LinkedInDiscovery()
    return discovery.discover_profiles(domain, company_name, mode)
