"""
Enhanced vetting service with keyword matching and e-commerce detection.

This service checks if discovered websites are relevant by:
1. Checking for e-commerce indicators (product, cart, checkout, shop, store)
2. Checking if the site content matches the search keywords
3. Scoring relevance based on keyword frequency
"""
import httpx
import re
import os
import json
import asyncio
from typing import Dict, List, Tuple, Optional
from bs4 import BeautifulSoup
import logging
import google.generativeai as genai
from app.db.mongodb_session import get_database

logger = logging.getLogger(__name__)

# Configure Gemini API
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# E-commerce indicators to look for
ECOMMERCE_KEYWORDS = ["product", "cart", "checkout", "shop", "store", "buy", "price", "add to cart"]

# Common words to ignore when checking keyword relevance
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "been", "be",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "this", "that", "these", "those"
}


def extract_domain_root(domain: str) -> str:
    """
    Extract the root domain (remove subdomains).
    Examples:
        www.example.com -> example.com
        shop.example.co.uk -> example.co.uk
    """
    parts = domain.lower().split('.')

    # Handle special TLDs like .co.uk, .com.au
    if len(parts) >= 3 and parts[-2] in ['co', 'com', 'net', 'org', 'ac']:
        return '.'.join(parts[-3:])
    elif len(parts) >= 2:
        return '.'.join(parts[-2:])

    return domain


async def fetch_homepage(domain: str, timeout: int = 40, max_retries: int = 3, stagger_delay: bool = True) -> Optional[str]:
    """
    Fetch homepage HTML content with retry logic and fallback strategies.

    Args:
        domain: Domain to fetch
        timeout: Request timeout in seconds (default: 40s for slow e-commerce sites)
        max_retries: Maximum number of retry attempts
        stagger_delay: Add small random delay to stagger concurrent requests (default: True)

    Returns:
        HTML content or None if all attempts fail
    """
    # Add random delay to stagger concurrent requests and avoid hammering sites
    if stagger_delay:
        import random
        delay = random.uniform(2.0, 5.0)  # Random delay between 2-5 seconds (more conservative)
        await asyncio.sleep(delay)

    # Multiple user agents to try (rotate to avoid detection)
    # Using diverse, recent user agents from real browsers
    user_agents = [
        # Chrome on Windows
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        # Chrome on Mac
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        # Firefox on Windows
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        # Safari on Mac
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        # Edge on Windows
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        # Chrome on Linux
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    # Pages to try in order (homepage, then fallback pages)
    pages_to_try = [
        "",           # Homepage
        "/products",  # Products page
        "/shop",      # Shop page
        "/about",     # About page
    ]

    for page in pages_to_try:
        url = f"https://{domain}{page}"

        for attempt in range(max_retries):
            try:
                headers = {
                    'User-Agent': user_agents[attempt % len(user_agents)],
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }

                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    verify=False  # Ignore SSL certificate errors
                ) as client:
                    response = await client.get(url, headers=headers)

                    if response.status_code == 200:
                        logger.info(f"Successfully fetched {url} (attempt {attempt + 1})")
                        return response.text
                    elif response.status_code == 429:
                        # Rate limiting - use aggressive backoff or give up early
                        if attempt >= 1:  # After 1st 429, give up on this page/domain
                            logger.warning(f"Repeated 429 for {url}, skipping to avoid further rate limiting")
                            break  # Move to next page or give up
                        wait_time = 10 + (2 ** attempt) * 5  # 10s, 20s, 40s backoff for rate limits
                        logger.warning(f"Status 429 (rate limit) for {url}, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(wait_time)
                        continue
                    elif response.status_code == 403:
                        # Bot detection - longer wait
                        if attempt >= 1:  # After 1st 403, give up on this page
                            logger.warning(f"Repeated 403 for {url}, likely bot detection - skipping")
                            break
                        wait_time = 5 + (2 ** attempt) * 3  # 5s, 11s, 23s backoff
                        logger.warning(f"Status 403 (forbidden) for {url}, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"Status {response.status_code} for {url}")
                        # Try next page for 4xx errors (except 403/429)
                        if 400 <= response.status_code < 500:
                            break

            except httpx.TimeoutException:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(f"Timeout fetching {url} (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time)
                continue

            except httpx.ConnectError:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(f"Connection error for {url} (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time)
                continue

            except Exception as e:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(f"Error fetching {url} (attempt {attempt + 1}/{max_retries}): {type(e).__name__}: {e}, waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time)
                continue

        # If we got here and it's not the last page, try next page
        if page != pages_to_try[-1]:
            logger.info(f"Failed to fetch {url}, trying next fallback page...")
            await asyncio.sleep(5)  # Wait 5 seconds between different page attempts to avoid rate limiting
            continue

    # All attempts failed
    logger.error(f"All fetch attempts failed for {domain}")
    return None


def calculate_domain_name_relevance(domain: str, keyword_variants: List[str]) -> float:
    """
    Calculate relevance score based on domain name alone.

    This catches highly relevant domains even if we can't fetch their content.
    Example: "just-keepers.com" should score high for goalkeeper-related searches.

    Args:
        domain: Domain name (e.g., "just-keepers.com")
        keyword_variants: List of keyword variants to match against

    Returns:
        Relevance score (0.0-1.0)
    """
    if not domain or not keyword_variants:
        return 0.0

    # Normalize domain name (remove TLD and hyphens/underscores)
    domain_lower = domain.lower()
    domain_parts = domain_lower.replace('.com', '').replace('.net', '').replace('.org', '').replace('.co.uk', '')
    domain_words = re.split(r'[-_.]', domain_parts)

    # Check how many keyword variants appear in domain name
    matches = 0
    for variant in keyword_variants:
        variant_lower = variant.lower()
        # Check if variant appears in domain name or any domain word
        if variant_lower in domain_lower or any(variant_lower in word for word in domain_words):
            matches += 1

    # Calculate score (multiple matches = higher relevance)
    if matches == 0:
        return 0.0
    elif matches == 1:
        return 0.3  # One match = 30% (passes min threshold)
    elif matches == 2:
        return 0.5  # Two matches = 50%
    else:
        return 0.7  # Three+ matches = 70%


def check_ecommerce_indicators(html: str) -> Tuple[bool, List[str]]:
    """
    Check if the page contains e-commerce indicators.
    Returns: (has_ecommerce, found_keywords)
    """
    if not html:
        return False, []

    text_lower = html.lower()
    found_keywords = []

    for keyword in ECOMMERCE_KEYWORDS:
        if keyword in text_lower:
            found_keywords.append(keyword)

    # More lenient: require at least 1 e-commerce keyword (down from 2)
    has_ecommerce = len(found_keywords) >= 1

    return has_ecommerce, found_keywords


def tokenize(text: str) -> List[str]:
    """Tokenize text into words, removing punctuation and stop words."""
    # Remove HTML tags if any
    text = re.sub(r'<[^>]+>', ' ', text)
    # Extract words (alphanumeric sequences)
    words = re.findall(r'\b[a-z0-9]+\b', text.lower())
    # Remove stop words and very short words
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


async def load_variants_from_db(keyword: str) -> Optional[List[str]]:
    """Load cached keyword variants from MongoDB."""
    try:
        db = await get_database()
        cache_collection = db['keyword_variants_cache']

        # Create a cache key (normalized lowercase)
        cache_key = keyword.lower().strip()

        # Look up in cache
        cached = await cache_collection.find_one({"keyword": cache_key})
        if cached:
            logger.info(f"Cache hit for keyword: {cache_key}")
            return cached.get("variants", [])

        logger.info(f"Cache miss for keyword: {cache_key}")
        return None
    except Exception as e:
        logger.warning(f"Error loading variants from cache: {e}")
        return None


async def save_variants_to_db(keyword: str, variants: List[str]) -> None:
    """Save keyword variants to MongoDB cache."""
    try:
        db = await get_database()
        cache_collection = db['keyword_variants_cache']

        # Create a cache key (normalized lowercase)
        cache_key = keyword.lower().strip()

        # Upsert the cache entry
        await cache_collection.update_one(
            {"keyword": cache_key},
            {
                "$set": {
                    "keyword": cache_key,
                    "variants": variants,
                    "updated_at": None  # Could add timestamp if needed
                }
            },
            upsert=True
        )
        logger.info(f"Cached {len(variants)} variants for keyword: {cache_key}")
    except Exception as e:
        logger.warning(f"Error saving variants to cache: {e}")


async def generate_keyword_variants_ai(keywords: List[str]) -> List[str]:
    """
    Generate keyword variants using Gemini AI with database caching.

    This function minimizes API costs by:
    1. Checking MongoDB cache first
    2. Only calling Gemini if not cached
    3. Caching results for future use

    Args:
        keywords: List of search keywords (e.g., ["Goalkeeper Gloves"])

    Returns:
        List of keyword variants including abbreviations, synonyms, and related terms
    """
    if not keywords:
        return []

    # Combine keywords into a single string for caching
    combined_keyword = " ".join(keywords)

    # Check cache first
    cached_variants = await load_variants_from_db(combined_keyword)
    if cached_variants is not None:
        return cached_variants

    # If not cached and Gemini is available, generate variants
    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY not set, using basic variants only")
        # Fallback to basic tokenization
        variants = set()
        for keyword in keywords:
            variants.add(keyword.lower())
            words = tokenize(keyword)
            variants.update(words)
        return list(variants)

    try:
        # Use Gemini to generate variants
        model = genai.GenerativeModel('gemini-2.5-flash')  # Using flash model for cost efficiency

        prompt = f"""Generate 5-10 common abbreviations, synonyms, and related search terms for: "{combined_keyword}"

Rules:
- Include common abbreviations (e.g., "goalkeeper" -> "gk", "goalie")
- Include singular and plural forms if relevant
- Include related industry terms
- Return ONLY a JSON array of strings, no explanation
- Keep terms concise and relevant for e-commerce product searches

Example for "Goalkeeper Gloves":
["goalkeeper", "gk", "goalie", "keeper", "gloves", "gk gloves", "goalie gloves", "goalkeeper glove", "keeper gloves"]

Now generate for: "{combined_keyword}"
"""

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Parse JSON response
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()

        variants_list = json.loads(response_text)

        if not isinstance(variants_list, list):
            raise ValueError("Response is not a list")

        # Add original keywords and tokenized words
        all_variants = set(variants_list)
        for keyword in keywords:
            all_variants.add(keyword.lower())
            words = tokenize(keyword)
            all_variants.update(words)

        final_variants = list(all_variants)

        # Cache the result
        await save_variants_to_db(combined_keyword, final_variants)

        logger.info(f"Generated {len(final_variants)} variants using Gemini for: {combined_keyword}")
        return final_variants

    except Exception as e:
        logger.error(f"Error generating variants with Gemini: {e}")
        # Fallback to basic variants
        variants = set()
        for keyword in keywords:
            variants.add(keyword.lower())
            words = tokenize(keyword)
            variants.update(words)
        return list(variants)


async def calculate_keyword_relevance(
    html: str,
    keywords: List[str],
    keyword_variants: Optional[List[str]] = None
) -> Dict:
    """
    Calculate how relevant the page is to the search keywords.

    Args:
        html: HTML content to analyze
        keywords: Original search keywords
        keyword_variants: Pre-generated keyword variants (optional). If provided,
                         skips AI generation to avoid duplicate API calls.

    Returns:
        {
            "score": float (0.0-1.0),
            "keyword_matches": {keyword: count},
            "total_matches": int,
            "found_keywords": List[str]
        }
    """
    if not html:
        return {
            "score": 0.0,
            "keyword_matches": {},
            "total_matches": 0,
            "found_keywords": []
        }

    # Parse HTML to get text content
    soup = BeautifulSoup(html, 'html.parser')

    # Remove script and style elements
    for script in soup(["script", "style", "nav", "footer"]):
        script.decompose()

    # Get text content
    text = soup.get_text(separator=' ', strip=True)
    text_lower = text.lower()

    # Use pre-generated variants if provided, otherwise generate them
    if keyword_variants is not None:
        all_keywords = keyword_variants
        logger.debug(f"Using pre-generated keyword variants ({len(all_keywords)} variants)")
    else:
        # Generate keyword variants using AI with caching
        all_keywords = await generate_keyword_variants_ai(keywords)
        logger.debug(f"Generated keyword variants on-demand ({len(all_keywords)} variants)")

    # Count keyword occurrences
    keyword_matches = {}
    total_matches = 0
    found_keywords = []

    for keyword in all_keywords:
        count = len(re.findall(r'\b' + re.escape(keyword) + r'\b', text_lower))
        if count > 0:
            keyword_matches[keyword] = count
            total_matches += count
            found_keywords.append(keyword)

    # Calculate relevance score (0.0-1.0)
    # Base score on: number of different keywords found + total frequency
    unique_keywords_score = min(len(found_keywords) / len(all_keywords), 1.0) * 0.6
    frequency_score = min(total_matches / 10.0, 1.0) * 0.4  # Cap at 10 mentions

    score = unique_keywords_score + frequency_score

    return {
        "score": round(score, 3),
        "keyword_matches": keyword_matches,
        "total_matches": total_matches,
        "found_keywords": found_keywords
    }


async def vet_domain(
    domain: str,
    search_keywords: List[str],
    min_ecommerce_keywords: int = 1,  # Lowered from 2 to 1
    min_relevance_score: float = 0.2,  # Lowered from 0.3 to 0.2
    keyword_variants: Optional[List[str]] = None
) -> Dict:
    """
    Vet a domain to determine if it's relevant to the search.

    Args:
        domain: Domain to vet (e.g., "example.com")
        search_keywords: Keywords used in the discovery search
        min_ecommerce_keywords: Minimum number of e-commerce keywords required (default: 1)
        min_relevance_score: Minimum relevance score (0.0-1.0) (default: 0.2)
        keyword_variants: Pre-generated keyword variants (optional). If provided,
                         skips AI generation to avoid duplicate API calls.

    Returns:
        {
            "domain": str,
            "status": "approved" | "rejected",
            "reason": str,
            "has_ecommerce": bool,
            "ecommerce_keywords": List[str],
            "relevance_score": float,
            "keyword_matches": Dict,
            "total_keyword_mentions": int
        }
    """
    # Generate keyword variants if not provided
    if keyword_variants is None:
        keyword_variants = await generate_keyword_variants_ai(search_keywords)

    # Calculate domain name relevance (before fetch attempt)
    domain_name_score = calculate_domain_name_relevance(domain, keyword_variants)

    # Fetch homepage
    html = await fetch_homepage(domain)

    if not html:
        # If fetch failed but domain name is highly relevant, approve it!
        if domain_name_score >= min_relevance_score:
            return {
                "domain": domain,
                "status": "approved",
                "reason": f"Approved by domain name relevance (score: {domain_name_score:.2f}) - fetch failed but domain name highly relevant",
                "has_ecommerce": True,  # Assume true for highly relevant domain names
                "ecommerce_keywords": ["domain-name-match"],
                "relevance_score": domain_name_score,
                "keyword_matches": {"domain_name": 1},
                "total_keyword_mentions": 1
            }
        else:
            return {
                "domain": domain,
                "status": "rejected",
                "reason": f"Could not fetch homepage (tried homepage, /products, /shop, /about) and domain name not relevant enough (score: {domain_name_score:.2f})",
                "has_ecommerce": False,
                "ecommerce_keywords": [],
                "relevance_score": domain_name_score,
                "keyword_matches": {},
                "total_keyword_mentions": 0
            }

    # Check for e-commerce indicators
    has_ecommerce, ecommerce_keywords = check_ecommerce_indicators(html)

    # Check keyword relevance from content
    relevance = await calculate_keyword_relevance(html, search_keywords, keyword_variants)

    # Combine content relevance with domain name relevance (take the higher score)
    combined_relevance_score = max(relevance["score"], domain_name_score)

    # Determine if domain passes vetting (more lenient criteria)
    approved = (
        has_ecommerce and
        len(ecommerce_keywords) >= min_ecommerce_keywords and
        combined_relevance_score >= min_relevance_score
    )

    # Generate reason
    if not has_ecommerce:
        reason = f"No e-commerce indicators found (need {min_ecommerce_keywords}, found {len(ecommerce_keywords)})"
    elif combined_relevance_score < min_relevance_score:
        reason = f"Low keyword relevance (content: {relevance['score']:.2f}, domain: {domain_name_score:.2f}, combined: {combined_relevance_score:.2f}, need >= {min_relevance_score})"
    else:
        domain_boost = " (domain name boost)" if domain_name_score > relevance["score"] else ""
        reason = f"Approved: Has e-commerce ({len(ecommerce_keywords)} keywords) and relevant content (score: {combined_relevance_score:.2f}{domain_boost})"

    return {
        "domain": domain,
        "status": "approved" if approved else "rejected",
        "reason": reason,
        "has_ecommerce": has_ecommerce,
        "ecommerce_keywords": ecommerce_keywords,
        "relevance_score": combined_relevance_score,
        "keyword_matches": relevance["keyword_matches"],
        "total_keyword_mentions": relevance["total_matches"]
    }


async def vet_domains_batch(
    domains: List[str],
    search_keywords: List[str],
    min_ecommerce_keywords: int = 1,  # Lowered from 2 to 1
    min_relevance_score: float = 0.2,  # Lowered from 0.3 to 0.2
    keyword_variants: Optional[List[str]] = None,
    max_concurrent: int = 5  # Very conservative to avoid rate limiting (reduced from 20)
) -> Tuple[List[Dict], List[Dict]]:
    """
    Vet multiple domains concurrently with aggressive rate limiting protection.

    Args:
        domains: List of domains to vet
        search_keywords: Original search keywords
        min_ecommerce_keywords: Minimum number of e-commerce keywords required (default: 1)
        min_relevance_score: Minimum relevance score (0.0-1.0) (default: 0.2)
        keyword_variants: Pre-generated keyword variants (optional). If provided,
                         skips AI generation to avoid duplicate API calls.
        max_concurrent: Maximum number of concurrent domain fetches (default: 5, very conservative)

    Returns:
        (approved_domains, rejected_domains)
        Each item is a dict with vetting details
    """
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(max_concurrent)

    async def vet_with_semaphore(domain: str):
        """Vet a single domain with semaphore to limit concurrency."""
        async with semaphore:
            return await vet_domain(domain, search_keywords, min_ecommerce_keywords, min_relevance_score, keyword_variants)

    # Vet all domains concurrently with rate limiting
    tasks = [vet_with_semaphore(domain) for domain in domains]
    results = await asyncio.gather(*tasks)

    # Separate approved and rejected
    approved = [r for r in results if r["status"] == "approved"]
    rejected = [r for r in results if r["status"] == "rejected"]

    logger.info(f"Vetting complete: {len(approved)} approved, {len(rejected)} rejected out of {len(domains)}")

    return approved, rejected
