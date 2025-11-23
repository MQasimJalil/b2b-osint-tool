"""
Website Contact Scraper

Intelligently scrapes company websites for contact information:
- Phone numbers
- WhatsApp numbers/links
- LinkedIn profiles
- Social media handles

Focuses on high-value pages: contact, about, team, homepage.
"""

import logging
import time
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
from pathlib import Path

try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError:
    httpx = None
    BeautifulSoup = None

from pipeline.contact_patterns import (
    extract_phones,
    extract_whatsapp,
    extract_linkedin,
    extract_social_media,
    ContactMatch
)

logger = logging.getLogger(__name__)


class WebsiteContactScraper:
    """Scrapes company websites for contact information."""

    # High-value page patterns (in priority order)
    CONTACT_PAGE_PATTERNS = [
        'contact', 'kontakt', 'contacto', 'contatto', 'nous-contacter',
        'get-in-touch', 'reach-us', 'contact-us'
    ]

    ABOUT_PAGE_PATTERNS = [
        'about', 'about-us', 'o-nas', 'uber-uns', 'quienes-somos',
        'chi-siamo', 'team', 'our-team', 'people', 'leadership'
    ]

    SOCIAL_INDICATORS = [
        'follow us', 'find us', 'connect', 'social media',
        'stay connected', 'join us'
    ]

    def __init__(
        self,
        timeout: int = 10,
        max_pages: int = 5,
        user_agent: str = None
    ):
        """
        Initialize website scraper.

        Args:
            timeout: Request timeout in seconds
            max_pages: Maximum pages to scrape per domain
            user_agent: Custom user agent string
        """
        self.timeout = timeout
        self.max_pages = max_pages
        self.user_agent = user_agent or (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        if not httpx or not BeautifulSoup:
            raise ImportError(
                "Required dependencies not installed. "
                "Run: pip install httpx beautifulsoup4"
            )

    def scrape_domain(
        self,
        domain: str,
        mode: str = 'lenient'
    ) -> Dict[str, List[ContactMatch]]:
        """
        Scrape a domain for contact information.

        Args:
            domain: Domain to scrape (e.g., 'example.com')
            mode: 'lenient' (homepage + contact) or 'aggressive' (all pages)

        Returns:
            Dict with keys: phones, whatsapp, linkedin, social_media
        """
        logger.info(f"[{domain}] Starting website scrape in {mode} mode")

        results = {
            'phones': [],
            'whatsapp': [],
            'linkedin': [],
            'social_media': {}
        }

        # Determine which pages to scrape
        pages_to_scrape = self._get_pages_to_scrape(domain, mode)

        # Scrape each page
        for page_url, page_type in pages_to_scrape[:self.max_pages]:
            try:
                html, text = self._fetch_page(page_url)
                if html:
                    page_results = self._extract_contacts_from_page(
                        html, text, page_url, page_type
                    )
                    self._merge_results(results, page_results)

                # Be nice to servers
                time.sleep(1)

            except Exception as e:
                logger.warning(f"[{domain}] Failed to scrape {page_url}: {e}")
                continue

        # Log summary
        logger.info(
            f"[{domain}] Found: {len(results['phones'])} phones, "
            f"{len(results['whatsapp'])} WhatsApp, "
            f"{len(results['linkedin'])} LinkedIn"
        )

        return results

    def _get_pages_to_scrape(
        self,
        domain: str,
        mode: str
    ) -> List[Tuple[str, str]]:
        """
        Determine which pages to scrape based on mode.

        Args:
            domain: Domain to scrape
            mode: 'lenient' or 'aggressive'

        Returns:
            List of (url, page_type) tuples
        """
        base_url = f'https://{domain}'
        pages = []

        # Always scrape homepage
        pages.append((base_url, 'homepage'))

        # Always try contact page
        for pattern in self.CONTACT_PAGE_PATTERNS[:3]:  # Top 3 patterns
            pages.append((f'{base_url}/{pattern}', 'contact'))

        if mode == 'aggressive':
            # Add about/team pages
            for pattern in self.ABOUT_PAGE_PATTERNS[:2]:
                pages.append((f'{base_url}/{pattern}', 'about'))

            # Try common social media page
            pages.append((f'{base_url}/social', 'social'))

        return pages

    def _fetch_page(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch a page and return HTML and text.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (html, text) or (None, None) on failure
        """
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                headers = {'User-Agent': self.user_agent}
                response = client.get(url, headers=headers)

                if response.status_code == 200:
                    html = response.text
                    soup = BeautifulSoup(html, 'html.parser')

                    # Remove script and style tags
                    for tag in soup(['script', 'style', 'meta', 'link']):
                        tag.decompose()

                    text = soup.get_text(separator=' ', strip=True)
                    return html, text

                else:
                    logger.debug(f"Failed to fetch {url}: HTTP {response.status_code}")
                    return None, None

        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            return None, None

    def _extract_contacts_from_page(
        self,
        html: str,
        text: str,
        url: str,
        page_type: str
    ) -> Dict[str, List[ContactMatch]]:
        """
        Extract contacts from a single page.

        Args:
            html: HTML content
            text: Plain text content
            url: Page URL
            page_type: Type of page (homepage, contact, about, etc.)

        Returns:
            Dict with extracted contacts
        """
        results = {
            'phones': [],
            'whatsapp': [],
            'linkedin': [],
            'social_media': {}
        }

        # Extract phone numbers
        phone_matches = extract_phones(text)
        for match in phone_matches:
            match.source = f'website_{page_type}'
            # Boost confidence if on contact page
            if page_type == 'contact':
                match.confidence = min(1.0, match.confidence + 0.2)
        results['phones'] = phone_matches

        # Extract WhatsApp
        whatsapp_matches = extract_whatsapp(text, html)
        for match in whatsapp_matches:
            match.source = f'website_{page_type}'
            if page_type == 'contact':
                match.confidence = min(1.0, match.confidence + 0.1)
        results['whatsapp'] = whatsapp_matches

        # Extract LinkedIn
        linkedin_matches = extract_linkedin(text, html)
        for match in linkedin_matches:
            match.source = f'website_{page_type}'
            # Higher confidence for LinkedIn on about/team pages
            if page_type in ['about', 'team']:
                match.confidence = min(1.0, match.confidence + 0.1)
        results['linkedin'] = linkedin_matches

        # Extract social media
        social_matches = extract_social_media(text, html)
        for platform, matches in social_matches.items():
            for match in matches:
                match.source = f'website_{page_type}'
                if platform not in results['social_media']:
                    results['social_media'][platform] = []
                results['social_media'][platform].append(match)

        # Special: Look for social media in footer
        soup = BeautifulSoup(html, 'html.parser')
        footer = soup.find('footer')
        if footer:
            footer_social = self._extract_footer_social(footer, url)
            for platform, match in footer_social.items():
                if platform not in results['social_media']:
                    results['social_media'][platform] = []
                results['social_media'][platform].append(match)

        return results

    def _extract_footer_social(
        self,
        footer_element,
        base_url: str
    ) -> Dict[str, ContactMatch]:
        """
        Extract social media links from footer.

        Args:
            footer_element: BeautifulSoup footer element
            base_url: Base URL for resolving relative links

        Returns:
            Dict mapping platform to ContactMatch
        """
        social_links = {}

        # Common social media domains
        platforms = {
            'facebook.com': 'facebook',
            'fb.com': 'facebook',
            'instagram.com': 'instagram',
            'twitter.com': 'twitter',
            'x.com': 'twitter',
            'linkedin.com': 'linkedin',
            'youtube.com': 'youtube',
            'tiktok.com': 'tiktok'
        }

        # Find all links in footer
        for link in footer_element.find_all('a', href=True):
            href = link.get('href', '')

            # Resolve relative URLs
            if href.startswith('/'):
                href = urljoin(base_url, href)

            # Check if it's a social media link
            for domain, platform in platforms.items():
                if domain in href.lower():
                    if platform not in social_links:
                        social_links[platform] = ContactMatch(
                            value=href,
                            type=f'social_{platform}',
                            confidence=0.9,  # High confidence for footer links
                            context='footer',
                            source='website_footer'
                        )
                    break

        return social_links

    def _merge_results(
        self,
        target: Dict[str, List],
        source: Dict[str, List]
    ):
        """
        Merge source results into target (in-place).

        Args:
            target: Target dict to merge into
            source: Source dict to merge from
        """
        for key in ['phones', 'whatsapp', 'linkedin']:
            if key in source:
                target[key].extend(source[key])

        # Special handling for social_media (dict of lists)
        if 'social_media' in source:
            for platform, matches in source['social_media'].items():
                if platform not in target['social_media']:
                    target['social_media'][platform] = []
                target['social_media'][platform].extend(matches)

    def scrape_contact_page(self, url: str) -> Dict[str, List[ContactMatch]]:
        """
        Quick method to scrape just a contact page.

        Args:
            url: Contact page URL

        Returns:
            Dict with extracted contacts
        """
        html, text = self._fetch_page(url)

        if not html:
            return {
                'phones': [],
                'whatsapp': [],
                'linkedin': [],
                'social_media': {}
            }

        return self._extract_contacts_from_page(html, text, url, 'contact')


# Convenience function
def scrape_company_website(domain: str, mode: str = 'lenient') -> Dict:
    """
    Quick function to scrape a company website.

    Args:
        domain: Company domain
        mode: 'lenient' or 'aggressive'

    Returns:
        Dict with contact results
    """
    scraper = WebsiteContactScraper()
    return scraper.scrape_domain(domain, mode)
