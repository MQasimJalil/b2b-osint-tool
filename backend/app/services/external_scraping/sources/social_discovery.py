"""
Social Media Profile Discovery

Intelligently discovers social media profiles using:
- Brand name variations (domain vs company name)
- Multiple platforms (LinkedIn, Instagram, Facebook, Twitter, etc.)
- Pattern-based queries (intext, site operators)
- Selenium-based verification for JavaScript-rendered links
"""

import logging
import re
import json
from typing import List, Dict, Optional, Set, Tuple
from urllib.parse import urlparse, unquote, parse_qs
from html import unescape
import requests
from requests.exceptions import RequestException
from dotenv import load_dotenv

from pipeline.sources.search_backend import SearchBackend

load_dotenv()

# BeautifulSoup for HTML parsing (optional)
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None

logger = logging.getLogger(__name__)

# Selenium imports (optional, for JavaScript-rendered content)
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available - verification will use basic requests only")


class SocialMediaDiscovery:
    """Discovers social media profiles across multiple platforms."""

    # Social media platforms to search
    PLATFORMS = {
        'linkedin': ['linkedin.com/company', 'linkedin.com/in'],
        'instagram': ['instagram.com'],
        'facebook': ['facebook.com'],
        'twitter': ['twitter.com', 'x.com'],
        'youtube': ['youtube.com/@', 'youtube.com/c/', 'youtube.com/channel/'],
        'tiktok': ['tiktok.com/@'],
    }

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        google_cx: Optional[str] = None,
        bing_api_key: Optional[str] = None,
        use_selenium: bool = True
    ):
        """
        Initialize social media discovery.

        Args:
            google_api_key: Google Custom Search API key
            google_cx: Google Custom Search Engine ID
            bing_api_key: Bing API key
            use_selenium: Use Selenium for JavaScript-rendered content verification
        """
        self.search_backend = SearchBackend(
            google_api_key=google_api_key,
            google_search_engine_id=google_cx,
            bing_api_key=bing_api_key
        )
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.driver = None

        if self.use_selenium:
            logger.info("Selenium verification enabled - will use headless browser for profile verification")
        else:
            logger.info("Selenium verification disabled - using basic requests only")

    def _get_driver(self):
        """Get or create Selenium driver (lazy initialization)."""
        if not self.use_selenium:
            return None

        if self.driver is None:
            try:
                logger.debug("Initializing headless Chrome driver...")
                options = uc.ChromeOptions()
                options.add_argument('--headless=new')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--mute-audio')
                options.add_argument('--disable-blink-features=AutomationControlled')
                options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

                self.driver = uc.Chrome(options=options, use_subprocess=False)


                logger.debug("Chrome driver initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Selenium driver: {e}")
                self.use_selenium = False
                self.driver = None

        return self.driver
    
    def close_driver(self):
        """Safely close Selenium driver."""
        if getattr(self, "driver", None):
            try:
                self.driver.quit()
                logger.debug("Chrome driver closed")
            except Exception as e:
                logger.debug(f"Error closing Chrome driver: {e}")
            finally:
                self.driver = None

    def discover_social_profiles(
        self,
        domain: str,
        company_name: Optional[str] = None,
        existing_social: Optional[Dict[str, str]] = None,
        mode: str = 'lenient'
    ) -> Dict[str, str]:
        """
        Discover social media profiles for a company.

        Args:
            domain: Company domain (e.g., 'sologk.com')
            company_name: Company name (e.g., 'Solo Goalkeeping')
            existing_social: Already extracted social links from profile
            mode: 'lenient' (basic platforms) or 'aggressive' (all platforms)

        Returns:
            Dict mapping platform to URL
        """
        logger.info(f"[{domain}] Discovering social media profiles in {mode} mode")

        results = {}

        # 1. Start with existing social links if available (filter out empty strings)
        if existing_social:
            # Only keep non-empty social links
            valid_existing = {k: v for k, v in existing_social.items() if v and v.strip()}
            if valid_existing:
                logger.info(f"[{domain}] Using {len(valid_existing)} existing social links")
                results.update(valid_existing)
            else:
                logger.info(f"[{domain}] No valid existing social links found (all empty)")

        # 2. Generate brand variations
        brand_variations = self._generate_brand_variations(domain, company_name)
        logger.info(f"[{domain}] Brand variations: {brand_variations}")

        # 3. Determine platforms to search
        platforms_to_search = list(self.PLATFORMS.keys())
        if mode == 'lenient':
            # Only search major platforms
            platforms_to_search = ['linkedin', 'instagram', 'facebook', 'twitter']

        # 4. Search for each platform with reverse link verification
        for platform in platforms_to_search:
            # Always search, even if we have existing link (to verify/update)
            # Pass domain for reverse link verification
            platform_urls = self._search_platform(
                platform,
                brand_variations,
                domain=domain,
                verify_links=True  # Enable reverse link verification
            )

            if platform_urls:
                # Take the first (most relevant) result
                new_url = platform_urls[0]

                # Check if we have a valid existing URL for this platform
                existing_url = results.get(platform, '')
                has_valid_existing = existing_url and existing_url.strip()

                if not has_valid_existing:
                    # No valid existing URL, use the new one
                    results[platform] = new_url
                    logger.info(f"[{domain}] Found {platform}: {new_url}")
                elif existing_url != new_url:
                    # Found a different URL - log it but keep existing (if existing is valid)
                    logger.info(f"[{domain}] Alternative {platform} found: {new_url} (keeping existing: {existing_url})")
            elif platform not in results or not results.get(platform, '').strip():
                # Didn't find anything and don't have valid existing
                logger.debug(f"[{domain}] No {platform} profile found")

        logger.info(f"[{domain}] Total social profiles found: {len(results)}")
        return results

    def _generate_brand_variations(
        self,
        domain: str,
        company_name: Optional[str]
    ) -> List[str]:
        """
        Generate brand name variations for searching.

        Args:
            domain: Company domain
            company_name: Company name (optional)

        Returns:
            List of brand variations to search
        """
        variations = []

        # 1. Domain stem (e.g., 'sologk' from 'sologk.com')
        domain_stem = domain.split('.')[0]
        variations.append(domain_stem)

        # 2. Domain stem with common separations
        # e.g., 'sologk' -> 'solo gk', 'solo-gk'
        if len(domain_stem) > 4:
            # Try to find word boundaries
            words = re.findall('[A-Z][a-z]*|[a-z]+|[0-9]+', domain_stem)
            if len(words) > 1:
                variations.append(' '.join(words))
                variations.append('-'.join(words))

        # 3. Company name if provided
        if company_name:
            variations.append(company_name)

            # Also add without spaces
            company_no_spaces = company_name.replace(' ', '').lower()
            if company_no_spaces not in variations:
                variations.append(company_no_spaces)

        # 4. Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for var in variations:
            var_lower = var.lower()
            if var_lower not in seen:
                seen.add(var_lower)
                unique_variations.append(var)

        return unique_variations

    def _search_platform(
        self,
        platform: str,
        brand_variations: List[str],
        domain: str = None,
        verify_links: bool = True
    ) -> List[str]:
        """
        Search for profiles on a specific platform.

        Args:
            platform: Platform name (e.g., 'instagram')
            brand_variations: List of brand name variations
            domain: Company domain for reverse link verification
            verify_links: Whether to verify profiles link back to domain

        Returns:
            List of found and verified profile URLs
        """
        platform_domains = self.PLATFORMS.get(platform, [])
        found_urls = []

        for domain_pattern in platform_domains:
            site = domain_pattern.split('/')[0]  # Extract base domain

            # Build query with all brand variations
            # e.g., site:instagram.com (intext:"sologk" OR intext:"Solo Goalkeeping")
            intext_parts = [f'intext:"{var}"' for var in brand_variations]
            query = f'site:{site} ({" OR ".join(intext_parts)})'

            try:
                results = self.search_backend.search(query, max_results=5)

                for result in results:
                    url = result.url
                    # Verify URL is actually for this platform
                    if site in url.lower():
                        # Verify it contains at least one brand variation
                        if self._verify_brand_match(url, result.title, result.snippet, brand_variations):
                            # Clean and normalize URL (strict profile-only filtering)
                            clean_url = self._clean_social_url(url, platform)
                            if clean_url and clean_url not in found_urls:
                                # Reverse link verification: check if profile links to domain
                                if verify_links and domain:
                                    if self._verify_profile_links_to_domain(clean_url, domain):
                                        found_urls.append(clean_url)
                                        logger.info(f"[{domain}] Verified {platform}: {clean_url}")
                                    else:
                                        logger.debug(f"[{domain}] Rejected {platform} {clean_url} - no link to domain")
                                else:
                                    # No verification requested, add directly
                                    found_urls.append(clean_url)

            except Exception as e:
                logger.debug(f"Search failed for {platform} with query: {query} - {e}")

        return found_urls

    def _verify_brand_match(
        self,
        url: str,
        title: str,
        snippet: str,
        brand_variations: List[str]
    ) -> bool:
        """
        Verify that a social media URL is actually for the target brand.

        Args:
            url: Social media URL
            title: Search result title
            snippet: Search result snippet
            brand_variations: List of brand variations

        Returns:
            True if verified match
        """
        # Combine all text for checking
        combined_text = f"{url} {title} {snippet}".lower()

        # Must contain at least one brand variation
        for variation in brand_variations:
            if variation.lower() in combined_text:
                return True

        return False

    def _verify_profile_links_to_domain(
        self,
        profile_url: str,
        domain: str,
        timeout: int = 15
    ) -> bool:
        """
        Verify that a social media profile links back to the company domain.

        Uses Selenium for JavaScript-rendered content (Instagram, Twitter, etc.)
        Falls back to requests for simple HTML sites.

        Handles platform-specific link formats:
        - Instagram: URL-encoded redirects (l.instagram.com/?u=...) rendered by JavaScript
        - Twitter/X: Shortened URLs (t.co) with domain in visible text
        - Facebook: Direct links or redirects
        - Others: Direct links or text mentions

        Args:
            profile_url: Social media profile URL
            domain: Company domain to look for (e.g., 'sologk.com' or 'www.sologk.com')
            timeout: Page load timeout in seconds

        Returns:
            True if profile links to domain, False otherwise
        """
        # Detect platform for platform-specific verification
        platform = self._detect_platform_from_url(profile_url)
        
        # Try Selenium first (for JavaScript-rendered content)
        if self.use_selenium:
            return self._verify_with_selenium(profile_url, domain, timeout, platform)
        else:
            # Fallback to basic requests
            return self._verify_with_requests(profile_url, domain, timeout, platform)
    
    def _detect_platform_from_url(self, url: str) -> Optional[str]:
        """Detect platform from URL."""
        url_lower = url.lower()
        if 'instagram.com' in url_lower:
            return 'instagram'
        elif 'twitter.com' in url_lower or 'x.com' in url_lower:
            return 'twitter'
        elif 'facebook.com' in url_lower or 'fb.com' in url_lower:
            return 'facebook'
        elif 'linkedin.com' in url_lower:
            return 'linkedin'
        elif 'youtube.com' in url_lower:
            return 'youtube'
        elif 'tiktok.com' in url_lower:
            return 'tiktok'
        return None
    
    def _generate_domain_patterns(self, domain: str) -> Tuple[List[str], List[str], List[str]]:
        """
        Generate comprehensive domain patterns for matching.
        
        Returns:
            Tuple of (base_patterns, url_encoded_patterns, subdomain_patterns)
        """
        domain_lower = domain.lower()
        base_domain = domain_lower.replace('www.', '')
        
        # Base patterns (exact domain matches)
        base_patterns = [
            base_domain,                          # sologk.com
            f'www.{base_domain}',                # www.sologk.com
            f'https://{base_domain}',            # https://sologk.com
            f'http://{base_domain}',             # http://sologk.com
            f'https://www.{base_domain}',        # https://www.sologk.com
            f'http://www.{base_domain}',         # http://www.sologk.com
            f'//{base_domain}',                  # //sologk.com
            f'//www.{base_domain}',              # //www.sologk.com
            f'{base_domain}/',                   # sologk.com/
            f'www.{base_domain}/',               # www.sologk.com/
        ]
        
        # URL-encoded versions (for Instagram l.instagram.com redirect links)
        # Include both uppercase and lowercase encodings (%3A vs %3a, %2F vs %2f)
        url_encoded_patterns = [
            f'http%3a%2f%2f{base_domain}',      # lowercase
            f'https%3a%2f%2f{base_domain}',     # lowercase
            f'http%3a%2f%2fwww.{base_domain}',  # lowercase
            f'https%3a%2f%2fwww.{base_domain}', # lowercase
            f'http%3A%2F%2F{base_domain}',      # uppercase
            f'https%3A%2F%2F{base_domain}',     # uppercase
            f'http%3A%2F%2Fwww.{base_domain}',  # uppercase
            f'https%3A%2F%2Fwww.{base_domain}', # uppercase
            f'%2f%2f{base_domain}',
            f'%2f%2fwww.{base_domain}',
            f'%2F%2F{base_domain}',
            f'%2F%2Fwww.{base_domain}',
        ]
        
        # Subdomain patterns (shop.domain.com, blog.domain.com, etc.)
        domain_stem = base_domain.split('.')[0]
        common_subdomains = ['shop', 'blog', 'store', 'www', 'mail', 'app', 'portal', 'secure']
        subdomain_patterns = []
        for subdomain in common_subdomains:
            subdomain_patterns.extend([
                f'{subdomain}.{base_domain}',
                f'https://{subdomain}.{base_domain}',
                f'http://{subdomain}.{base_domain}',
            ])
        
        return base_patterns, url_encoded_patterns, subdomain_patterns

    def _extract_links_from_html(self, html: str) -> Dict[str, List[str]]:
        """
        Extract all possible links from HTML using multiple methods.
        
        Returns:
            Dict with keys: hrefs, meta_tags, data_attributes, structured_data, link_texts
        """
        results = {
            'hrefs': [],
            'meta_tags': [],
            'data_attributes': [],
            'structured_data': [],
            'link_texts': [],
            'all_text': ''
        }
        
        if not html:
            return results
        
        html_lower = html.lower()
        results['all_text'] = html_lower
        
        # 1. Extract href attributes from <a> tags
        href_pattern = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\']', re.IGNORECASE)
        results['hrefs'] = href_pattern.findall(html)
        
        # 2. Extract link text from <a> tags (including nested elements)
        # Use BeautifulSoup if available for better nested element handling
        if BS4_AVAILABLE and BeautifulSoup:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if href:
                        # Get all text content including nested elements
                        link_text = link.get_text(strip=True)
                        if link_text:
                            results['link_texts'].append(link_text.lower())
                        if href not in results['hrefs']:
                            results['hrefs'].append(href)
            except Exception as e:
                logger.debug(f"Error using BeautifulSoup for link extraction: {e}")
                # Fallback to regex
                link_text_pattern = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
                link_matches = link_text_pattern.findall(html)
                for href, text_content in link_matches:
                    clean_text = re.sub(r'<[^>]+>', ' ', text_content).strip()
                    if clean_text:
                        results['link_texts'].append(clean_text.lower())
                    if href not in results['hrefs']:
                        results['hrefs'].append(href)
        else:
            # Regex fallback
            link_text_pattern = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
            link_matches = link_text_pattern.findall(html)
            for href, text_content in link_matches:
                clean_text = re.sub(r'<[^>]+>', ' ', text_content).strip()
                if clean_text:
                    results['link_texts'].append(clean_text.lower())
                if href not in results['hrefs']:
                    results['hrefs'].append(href)
        
        # Also extract standalone hrefs that might not have been captured above
        standalone_href_pattern = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\']', re.IGNORECASE)
        all_hrefs = standalone_href_pattern.findall(html)
        for href in all_hrefs:
            if href not in results['hrefs']:
                results['hrefs'].append(href)
        
        # 3. Extract from meta tags (og:url, twitter:url, canonical, etc.)
        meta_patterns = [
            r'<meta\s+[^>]*(?:property|name)=["\'](?:og:url|twitter:url|canonical)["\'][^>]*content=["\']([^"\']+)["\']',
            r'<link\s+[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
        ]
        for pattern in meta_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            results['meta_tags'].extend(matches)
        
        # 4. Extract from data attributes (data-href, data-url, data-link)
        data_pattern = re.compile(r'data-(?:href|url|link)=["\']([^"\']+)["\']', re.IGNORECASE)
        results['data_attributes'] = data_pattern.findall(html)
        
        # 5. Extract from structured data (JSON-LD)
        if BS4_AVAILABLE and BeautifulSoup:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                # Find JSON-LD scripts
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(script.string)
                        # Recursively search for URLs in JSON
                        urls = self._extract_urls_from_json(data)
                        results['structured_data'].extend(urls)
                    except (json.JSONDecodeError, AttributeError):
                        continue
                
                # Extract from microdata
                for element in soup.find_all(attrs={'itemprop': True}):
                    if element.get('href'):
                        results['structured_data'].append(element['href'])
                    if element.get('content'):
                        results['structured_data'].append(element['content'])
            except Exception as e:
                logger.debug(f"Error parsing HTML with BeautifulSoup: {e}")
        
        # 6. Extract JavaScript variables containing URLs
        js_url_pattern = re.compile(r'(?:url|href|link|website|domain)\s*[:=]\s*["\']([^"\']+)["\']', re.IGNORECASE)
        js_matches = js_url_pattern.findall(html)
        results['data_attributes'].extend(js_matches)
        
        return results
    
    def _extract_urls_from_json(self, data: any, urls: Optional[List[str]] = None) -> List[str]:
        """Recursively extract URLs from JSON data."""
        if urls is None:
            urls = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                if key in ['url', 'href', 'link', 'website', 'sameAs', 'urls']:
                    if isinstance(value, str) and ('http' in value.lower() or '.' in value):
                        urls.append(value)
                    elif isinstance(value, list):
                        urls.extend([v for v in value if isinstance(v, str) and ('http' in v.lower() or '.' in v)])
                else:
                    self._extract_urls_from_json(value, urls)
        elif isinstance(data, list):
            for item in data:
                self._extract_urls_from_json(item, urls)
        
        return urls
    
    def _verify_with_selenium(
        self,
        profile_url: str,
        domain: str,
        timeout: int = 15,
        platform: Optional[str] = None
    ) -> bool:
        """Verify profile using Selenium (handles JavaScript-rendered links)."""
        driver = self._get_driver()
        if driver is None:
            # Fallback to requests if driver initialization failed
            return self._verify_with_requests(profile_url, domain, timeout, platform)

        try:
            logger.debug(f"[{domain}] Loading {profile_url} with Selenium...")
            driver.set_page_load_timeout(timeout)
            driver.get(profile_url)

            # Wait for page to load (wait for body element)
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Platform-specific waits
            if platform == 'instagram':
                # Wait for bio section or link container
                try:
                    WebDriverWait(driver, 10).until(
                        EC.any_of(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='l.instagram.com']")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='user-bio']")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='http']"))
                        )
                    )
                except TimeoutException:
                    pass  # Continue anyway
            elif platform == 'twitter' or platform == 'x':
                # Wait for bio section
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='UserDescription']"))
                    )
                except TimeoutException:
                    pass
            
            # Scroll to ensure content is loaded
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            import time
            time.sleep(3)  # Wait for dynamic content
            
            # Scroll back up
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Get page source after JavaScript execution
            page_html = driver.page_source
            
            # Also try to extract from DOM elements directly
            dom_links = []
            try:
                # Find all links in the page
                link_elements = driver.find_elements(By.TAG_NAME, "a")
                for elem in link_elements[:50]:  # Limit to first 50 links
                    try:
                        href = elem.get_attribute('href')
                        if href:
                            dom_links.append(href)
                        text = elem.text
                        if text:
                            dom_links.append(text)
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"[{domain}] Error extracting DOM links: {e}")

            # Extract links using enhanced extraction
            extracted = self._extract_links_from_html(page_html)
            
            # Add DOM-extracted links
            extracted['hrefs'].extend(dom_links)
            
            # Generate domain patterns
            base_patterns, url_encoded_patterns, subdomain_patterns = self._generate_domain_patterns(domain)
            all_patterns = base_patterns + url_encoded_patterns + subdomain_patterns

            # Check all extracted sources
            verification_result = self._check_domain_in_extracted(
                extracted, all_patterns, domain, profile_url
            )
            
            if verification_result:
                return True

            # Check for domain stem with common TLDs (fallback)
            base_domain = domain.lower().replace('www.', '')
            domain_stem = base_domain.split('.')[0]
            if len(domain_stem) >= 5:
                tld_patterns = [
                    f'{domain_stem}.com',
                    f'{domain_stem}.co.uk',
                    f'{domain_stem}.io',
                    f'{domain_stem}.net',
                    f'{domain_stem}.org',
                ]
                verification_result = self._check_domain_in_extracted(
                    extracted, tld_patterns, domain, profile_url
                )
                if verification_result:
                    return True

            logger.warning(f"[{domain}] Profile {profile_url} NOT VERIFIED - no link to domain found")
            logger.debug(f"[{domain}] Checked {len(extracted['hrefs'])} hrefs, {len(extracted['meta_tags'])} meta tags, "
                        f"{len(extracted['data_attributes'])} data attributes, {len(extracted['structured_data'])} structured data")
            
            # Log sample of extracted links for debugging (first 3 of each type)
            if logger.isEnabledFor(logging.DEBUG):
                sample_hrefs = extracted['hrefs'][:3]
                if sample_hrefs:
                    logger.debug(f"[{domain}] Sample hrefs: {sample_hrefs}")
                sample_meta = extracted['meta_tags'][:3]
                if sample_meta:
                    logger.debug(f"[{domain}] Sample meta tags: {sample_meta}")
            
            return False

        except TimeoutException:
            logger.debug(f"[{domain}] Page load timeout for {profile_url}")
            # Timeout is not necessarily a failure - assume valid
            logger.info(f"[{domain}] Profile {profile_url} ASSUMED VALID (timeout)")
            return True

        except WebDriverException as e:
            logger.debug(f"[{domain}] WebDriver error for {profile_url}: {e}")
            # Driver errors shouldn't block discovery
            logger.info(f"[{domain}] Profile {profile_url} ASSUMED VALID (driver error)")
            return True

        except Exception as e:
            logger.warning(f"[{domain}] Error verifying {profile_url}: {e}")
            # On unexpected errors, assume valid to be safe
            return True
    
    def _check_domain_in_extracted(
        self,
        extracted: Dict[str, List[str]],
        patterns: List[str],
        domain: str,
        profile_url: str
    ) -> bool:
        """Check if any pattern matches in extracted links."""
        # Check hrefs
        for href in extracted['hrefs']:
            href_lower = href.lower()
            href_decoded = unquote(href_lower)
            
            for pattern in patterns:
                # Check in href directly
                if pattern in href_lower or pattern in href_decoded:
                    logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in href: {href[:100]}")
                    return True
                
                # Check URL parameters (for Instagram l.instagram.com/?u=...)
                try:
                    parsed = urlparse(href)
                    if parsed.query:
                        params = parse_qs(parsed.query)
                        # Check 'u' parameter specifically (Instagram redirect)
                        if 'u' in params:
                            for param_value in params['u']:
                                # Check encoded version (case-insensitive)
                                param_lower = param_value.lower()
                                if pattern in param_lower:
                                    logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in Instagram redirect param (encoded): {param_value[:100]}")
                                    return True
                                # Check decoded version
                                param_decoded = unquote(param_value)
                                if pattern in param_decoded.lower():
                                    logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in Instagram redirect param (decoded): {param_decoded[:100]}")
                                    return True
                        # Check all other parameters
                        for param_name, param_values in params.items():
                            for param_value in param_values:
                                param_lower = param_value.lower()
                                param_decoded = unquote(param_value)
                                # Check both encoded and decoded versions
                                if pattern in param_lower or pattern in param_decoded.lower():
                                    logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in URL param '{param_name}': {param_value[:100]}")
                                    return True
                except Exception as e:
                    logger.debug(f"[{domain}] Error parsing href {href[:100]}: {e}")
                    continue
        
        # Check meta tags
        for meta_url in extracted['meta_tags']:
            meta_lower = meta_url.lower()
            for pattern in patterns:
                if pattern in meta_lower:
                    logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in meta tag")
                    return True
        
        # Check data attributes
        for data_url in extracted['data_attributes']:
            data_lower = data_url.lower()
            data_decoded = unquote(data_lower)
            for pattern in patterns:
                if pattern in data_lower or pattern in data_decoded:
                    logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in data attribute")
                    return True
        
        # Check structured data
        for struct_url in extracted['structured_data']:
            struct_lower = struct_url.lower()
            for pattern in patterns:
                if pattern in struct_lower:
                    logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in structured data")
                    return True
        
        # Check link text (important for Twitter/X where domain is in visible text, not href)
        for link_text in extracted['link_texts']:
            if link_text.strip():
                link_text_lower = link_text.lower().strip()
                for pattern in patterns:
                    # Check if pattern matches in link text
                    if pattern in link_text_lower:
                        logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in link text: '{link_text_lower[:100]}'")
                        return True
                    # Also check if link text exactly matches domain (for cases like "sologk.com" as text)
                    base_domain = domain.lower().replace('www.', '')
                    if link_text_lower == base_domain or link_text_lower == f'www.{base_domain}':
                        logger.info(f"[{domain}] Profile {profile_url} VERIFIED - link text exactly matches domain: '{link_text_lower}'")
                        return True
        
        # Check all text content
        for pattern in patterns:
            if pattern in extracted['all_text']:
                logger.info(f"[{domain}] Profile {profile_url} VERIFIED - found '{pattern}' in page text")
                return True
        
        return False

    def _follow_redirect(self, url: str, max_redirects: int = 5, timeout: int = 10) -> Optional[str]:
        """Follow redirects to get final URL (especially for t.co links)."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
            return response.url
        except Exception as e:
            logger.debug(f"Error following redirect for {url}: {e}")
            return None
    
    def _verify_with_requests(
        self,
        profile_url: str,
        domain: str,
        timeout: int = 10,
        platform: Optional[str] = None
    ) -> bool:
        """Verify profile using basic requests (fallback for non-JavaScript sites)."""
        try:
            # Fetch profile page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(profile_url, headers=headers, timeout=timeout, allow_redirects=True)
            response.raise_for_status()

            # Decode HTML entities first (convert &amp; to &, etc.)
            page_html = unescape(response.text)

            # Extract links using enhanced extraction
            extracted = self._extract_links_from_html(page_html)
            
            # Platform-specific enhancements
            if platform == 'twitter' or platform == 'x':
                # Follow t.co redirects to get actual URLs
                t_co_links = [href for href in extracted['hrefs'] if 't.co/' in href.lower()]
                for t_co_link in t_co_links[:5]:  # Limit to first 5 to avoid too many requests
                    try:
                        final_url = self._follow_redirect(t_co_link, timeout=5)
                        if final_url and final_url not in extracted['hrefs']:
                            extracted['hrefs'].append(final_url)
                            logger.debug(f"[{domain}] Followed t.co redirect: {t_co_link} -> {final_url}")
                    except Exception as e:
                        logger.debug(f"[{domain}] Could not follow t.co redirect {t_co_link}: {e}")

            # Debug logging
            logger.debug(f"[{domain}] Checking {profile_url}")
            logger.debug(f"[{domain}] Found {len(extracted['hrefs'])} hrefs, {len(extracted['meta_tags'])} meta tags, "
                        f"{len(extracted['data_attributes'])} data attributes, {len(extracted['structured_data'])} structured data, "
                        f"{len(extracted['link_texts'])} link texts")

            # Generate domain patterns
            base_patterns, url_encoded_patterns, subdomain_patterns = self._generate_domain_patterns(domain)
            all_patterns = base_patterns + url_encoded_patterns + subdomain_patterns

            # Check all extracted sources
            verification_result = self._check_domain_in_extracted(
                extracted, all_patterns, domain, profile_url
            )
            
            if verification_result:
                return True

            # Check for domain stem with common TLDs (fallback)
            base_domain = domain.lower().replace('www.', '')
            domain_stem = base_domain.split('.')[0]
            if len(domain_stem) >= 5:  # Only for reasonably unique stems
                tld_patterns = [
                    f'{domain_stem}.com',
                    f'{domain_stem}.co.uk',
                    f'{domain_stem}.io',
                    f'{domain_stem}.net',
                    f'{domain_stem}.org',
                ]
                
                verification_result = self._check_domain_in_extracted(
                    extracted, tld_patterns, domain, profile_url
                )
                if verification_result:
                    return True

            logger.warning(f"[{domain}] Profile {profile_url} NOT VERIFIED - no link to domain found")
            logger.debug(f"[{domain}] Checked {len(extracted['hrefs'])} hrefs, {len(extracted['meta_tags'])} meta tags, "
                        f"{len(extracted['data_attributes'])} data attributes, {len(extracted['structured_data'])} structured data")
            
            # Log sample of extracted links for debugging (first 3 of each type)
            if logger.isEnabledFor(logging.DEBUG):
                sample_hrefs = extracted['hrefs'][:3]
                if sample_hrefs:
                    logger.debug(f"[{domain}] Sample hrefs: {sample_hrefs}")
                sample_meta = extracted['meta_tags'][:3]
                if sample_meta:
                    logger.debug(f"[{domain}] Sample meta tags: {sample_meta}")
            
            return False

        except RequestException as e:
            logger.debug(f"[{domain}] Failed to verify profile {profile_url}: {e}")
            # If we can't verify due to network issues, assume it's valid
            # (network issues shouldn't block discovery)
            logger.info(f"[{domain}] Profile {profile_url} ASSUMED VALID (verification failed: {e})")
            return True

        except Exception as e:
            logger.warning(f"[{domain}] Error verifying profile {profile_url}: {e}")
            # On unexpected errors, assume valid to be safe
            return True

    def _clean_social_url(self, url: str, platform: str) -> Optional[str]:
        """
        Clean and normalize a social media URL.

        STRICT: Only allows main profile URLs, not posts/photos/videos.

        Args:
            url: Raw social media URL
            platform: Platform name

        Returns:
            Cleaned URL or None if invalid
        """
        try:
            # Remove query parameters and fragments
            url = url.split('?')[0].split('#')[0]

            # Remove trailing slashes
            url = url.rstrip('/')

            # Platform-specific cleaning - STRICT profile-only filtering
            if platform == 'linkedin':
                # Only company or individual profiles
                if '/company/' in url or '/in/' in url:
                    # Exclude posts, jobs, etc.
                    if any(x in url for x in ['/posts/', '/jobs/', '/feed/', '/updates/']):
                        return None
                    return url
                return None

            elif platform == 'instagram':
                # Only profiles (username pages)
                # Exclude: posts (/p/), reels (/reel/), stories (/stories/), TV (/tv/)
                if any(x in url for x in ['/p/', '/reel/', '/stories/', '/tv/', '/explore/']):
                    return None
                # Must be a profile: instagram.com/username format
                parts = url.split('/')
                if len(parts) >= 4 and parts[3]:  # Has username after domain
                    return url
                return None

            elif platform == 'facebook':
                # Only profiles and pages
                # Exclude: posts, photos, videos, events, groups
                exclude_patterns = [
                    '/posts/', '/photo', '/photos/', '/videos/', '/events/',
                    '/groups/', '/watch/', '/marketplace/', '/people/'
                ]
                if any(x in url for x in exclude_patterns):
                    return None
                return url

            elif platform in ['twitter', 'x']:
                # Only profiles
                # Exclude: tweets (/status/), moments (/moments/), lists (/lists/)
                if any(x in url for x in ['/status/', '/moments/', '/lists/', '/i/']):
                    return None
                return url

            elif platform == 'youtube':
                # Only channel/user pages
                # Must have @, /c/, or /channel/ in URL
                if any(x in url for x in ['/@', '/c/', '/channel/', '/user/']):
                    # Exclude: videos (/watch), playlists (/playlist)
                    if any(x in url for x in ['/watch', '/playlist']):
                        return None
                    return url
                return None

            elif platform == 'tiktok':
                # Only user profiles
                # Must have /@ in URL (user profile)
                if '/@' in url:
                    # Exclude: videos (/video/)
                    if '/video/' in url:
                        return None
                    return url
                return None

            else:
                # Unknown platform - return cleaned URL
                return url

        except Exception as e:
            logger.debug(f"Failed to clean URL {url}: {e}")
            return None

        return None


def discover_social_profiles(
    domain: str,
    company_name: Optional[str] = None,
    existing_social: Optional[Dict[str, str]] = None,
    mode: str = 'lenient'
) -> Dict[str, str]:
    """
    Quick function to discover social media profiles.

    Args:
        domain: Company domain
        company_name: Company name (optional)
        existing_social: Already extracted social links
        mode: Discovery mode

    Returns:
        Dict mapping platform to URL
    """
    discovery = SocialMediaDiscovery()
    return discovery.discover_social_profiles(domain, company_name, existing_social, mode)
