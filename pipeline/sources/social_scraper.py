"""
Social Media Contact Extraction

Finds social media profiles and extracts contact information
from Instagram, Facebook, Twitter/X bio/about sections.

Focuses on finding WhatsApp links and contact info in social bios.
"""

import logging
import time
from typing import Dict, List, Optional

try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError:
    httpx = None
    BeautifulSoup = None

from pipeline.contact_patterns import (
    extract_phones,
    extract_whatsapp,
    ContactMatch
)

logger = logging.getLogger(__name__)


class SocialMediaScraper:
    """Scrapes social media profiles for contact information."""

    def __init__(self, timeout: int = 10):
        """
        Initialize social media scraper.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

        if not httpx or not BeautifulSoup:
            raise ImportError(
                "Required dependencies not installed. "
                "Run: pip install httpx beautifulsoup4"
            )

    def scrape_social_profiles(
        self,
        social_links: Dict[str, str]
    ) -> Dict[str, List[ContactMatch]]:
        """
        Scrape social media profiles for contact info.

        Args:
            social_links: Dict mapping platform to URL

        Returns:
            Dict with keys: phones, whatsapp
        """
        results = {
            'phones': [],
            'whatsapp': []
        }

        for platform, url in social_links.items():
            if not url or not url.strip():
                continue

            try:
                contacts = self._scrape_platform(platform, url)
                results['phones'].extend(contacts['phones'])
                results['whatsapp'].extend(contacts['whatsapp'])

                time.sleep(2)  # Rate limiting

            except Exception as e:
                logger.debug(f"Failed to scrape {platform} ({url}): {e}")
                continue

        return results

    def _scrape_platform(
        self,
        platform: str,
        url: str
    ) -> Dict[str, List[ContactMatch]]:
        """
        Scrape a single social media platform.

        Args:
            platform: Platform name (instagram, facebook, twitter)
            url: Profile URL

        Returns:
            Dict with extracted contacts
        """
        results = {
            'phones': [],
            'whatsapp': []
        }

        # Fetch page
        html, text = self._fetch_page(url)
        if not html:
            return results

        # Extract contacts based on platform
        if platform == 'instagram':
            results = self._extract_instagram_contacts(html, text)
        elif platform == 'facebook':
            results = self._extract_facebook_contacts(html, text)
        elif platform in ['twitter', 'x']:
            results = self._extract_twitter_contacts(html, text)

        # Mark source
        for match in results.get('phones', []):
            match.source = f'social_{platform}'

        for match in results.get('whatsapp', []):
            match.source = f'social_{platform}'

        return results

    def _fetch_page(self, url: str) -> tuple:
        """Fetch page content."""
        try:
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            }

            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url, headers=headers)

                if response.status_code == 200:
                    html = response.text
                    soup = BeautifulSoup(html, 'html.parser')
                    text = soup.get_text(separator=' ', strip=True)
                    return html, text

        except Exception as e:
            logger.debug(f"Fetch error for {url}: {e}")

        return None, None

    def _extract_instagram_contacts(
        self,
        html: str,
        text: str
    ) -> Dict[str, List[ContactMatch]]:
        """Extract contacts from Instagram bio."""
        results = {'phones': [], 'whatsapp': []}

        # Instagram often has WhatsApp links in bio
        whatsapp_matches = extract_whatsapp(text, html)
        results['whatsapp'] = whatsapp_matches

        # Sometimes phone numbers in bio
        phone_matches = extract_phones(text, context_chars=100)
        results['phones'] = phone_matches

        return results

    def _extract_facebook_contacts(
        self,
        html: str,
        text: str
    ) -> Dict[str, List[ContactMatch]]:
        """Extract contacts from Facebook page."""
        results = {'phones': [], 'whatsapp': []}

        # Facebook business pages have contact sections
        phone_matches = extract_phones(text, context_chars=100)
        whatsapp_matches = extract_whatsapp(text, html)

        results['phones'] = phone_matches
        results['whatsapp'] = whatsapp_matches

        return results

    def _extract_twitter_contacts(
        self,
        html: str,
        text: str
    ) -> Dict[str, List[ContactMatch]]:
        """Extract contacts from Twitter/X bio."""
        results = {'phones': [], 'whatsapp': []}

        # Twitter bios sometimes have contact info
        phone_matches = extract_phones(text, context_chars=100)
        whatsapp_matches = extract_whatsapp(text, html)

        results['phones'] = phone_matches
        results['whatsapp'] = whatsapp_matches

        return results


# Convenience function
def scrape_social_media(social_links: Dict[str, str]) -> Dict:
    """
    Quick function to scrape social media profiles.

    Args:
        social_links: Dict mapping platform to URL

    Returns:
        Dict with contact results
    """
    scraper = SocialMediaScraper()
    return scraper.scrape_social_profiles(social_links)
