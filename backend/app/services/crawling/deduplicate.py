"""
Domain deduplication system to detect duplicate companies before crawling.
CLOUD-SAFE: Uses MongoDB only, no filesystem dependencies.

Flow:
1. Pattern match domain against already-crawled domains (40% weight)
2. If pattern score >= 20%, fetch homepage and compare (60% weight)
3. If total score >= 70%, mark as duplicate and skip crawling
"""

import os
import json
import re
import requests
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from datetime import datetime
import asyncio


# ============================================================================
# MongoDB Collections Access (Cloud-Safe)
# ============================================================================

async def get_mongodb():
    """Get MongoDB database connection."""
    from app.db.mongodb_session import get_database
    return await get_database()


async def track_crawled_domain(domain: str):
    """
    Add domain to crawled domains collection.
    Call this after successfully crawling a domain.
    """
    db = await get_mongodb()
    await db['crawled_domains'].update_one(
        {"domain": domain},
        {
            "$set": {
                "domain": domain,
                "crawled_at": datetime.utcnow(),
                "last_updated": datetime.utcnow()
            }
        },
        upsert=True
    )


async def get_crawled_domains() -> List[str]:
    """
    Get list of all previously crawled domains from MongoDB.
    """
    db = await get_mongodb()
    cursor = db['crawled_domains'].find({}, {"domain": 1, "_id": 0})
    domains = [doc["domain"] async for doc in cursor]
    return domains


async def save_homepage_features(domain: str, features: Dict):
    """Save homepage features to MongoDB for future comparisons."""
    db = await get_mongodb()
    await db['homepage_features'].update_one(
        {"domain": domain},
        {
            "$set": {
                "domain": domain,
                "extracted_at": datetime.utcnow(),
                "features": features
            }
        },
        upsert=True
    )


async def load_homepage_features(domain: str) -> Optional[Dict]:
    """Load cached homepage features from MongoDB."""
    db = await get_mongodb()
    doc = await db['homepage_features'].find_one({"domain": domain})
    if doc:
        return doc.get("features")
    return None


async def save_dedup_result(result: Dict):
    """Save deduplication result to MongoDB."""
    db = await get_mongodb()
    await db['dedup_results'].insert_one(result)


# ============================================================================
# Pattern Matching (40% weight)
# ============================================================================

def extract_brand_name(domain: str) -> str:
    """
    Extract brand/company name from domain.
    Examples:
        theoneglove.com -> theoneglove
        renegade-gk.co.uk -> renegadegk
        nike.com -> nike
    """
    # Remove TLD
    base = domain.split('.')[0]

    # Remove common suffixes
    for suffix in ['store', 'shop', 'direct', 'global', 'official']:
        if base.endswith(suffix):
            base = base[:-len(suffix)]

    # Remove separators for normalization
    normalized = base.replace('-', '').replace('_', '').replace('gk', 'goalkeeper')

    return normalized.lower().strip()


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def calculate_pattern_score(domain1: str, domain2: str) -> float:
    """
    Compare domain names for similarity.
    Returns score 0.0-0.40 (40% weight)
    """
    base1 = extract_brand_name(domain1)
    base2 = extract_brand_name(domain2)

    # Exact base match, different TLD
    if base1 == base2 and domain1.split('.')[-1] != domain2.split('.')[-1]:
        return 0.40

    # Similar with separators normalized
    normalized1 = domain1.split('.')[0].replace('-', '').replace('_', '').lower()
    normalized2 = domain2.split('.')[0].replace('-', '').replace('_', '').lower()
    if normalized1 == normalized2:
        return 0.35

    # Fuzzy match (1-2 character difference)
    edit_distance = levenshtein_distance(base1, base2)
    if edit_distance == 1:
        return 0.35
    elif edit_distance == 2:
        return 0.30

    # One contains the other
    if base1 in base2 or base2 in base1:
        return 0.25

    return 0.0


def find_pattern_matches(domain: str, already_crawled: List[str], threshold: float = 0.20) -> Dict[str, float]:
    """
    Find domains that match the pattern above threshold.

    Returns:
        {domain: pattern_score} for matches above threshold
    """
    matches = {}

    for existing_domain in already_crawled:
        score = calculate_pattern_score(domain, existing_domain)
        if score >= threshold:
            matches[existing_domain] = score

    return matches


# ============================================================================
# Homepage Feature Extraction (60% weight)
# ============================================================================

def fetch_homepage(domain: str, timeout: int = 10) -> Optional[str]:
    """
    Fetch ONLY the homepage HTML (1 page, lightweight).
    """
    url = f"https://{domain}"
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        if response.status_code == 200:
            return response.text
        return None
    except Exception as e:
        print(f"[WARNING] Could not fetch homepage for {domain}: {e}")
        return None


def extract_homepage_features_regex(html: str, domain: str) -> Dict:
    """
    Extract homepage features using REGEX/HEURISTICS (fast, free).

    Returns:
        {
            "company_name": str,
            "title": str,
            "description": str,
            "emails": [str],
            "social": {platform: username}
        }
    """
    soup = BeautifulSoup(html, 'html.parser')

    features = {
        "company_name": "",
        "title": "",
        "description": "",
        "emails": [],
        "social": {}
    }

    # Extract title
    title_tag = soup.find('title')
    if title_tag:
        features["title"] = title_tag.get_text().strip()

    # Extract company name from meta tags or title
    og_site_name = soup.find('meta', property='og:site_name')
    if og_site_name and og_site_name.get('content'):
        features["company_name"] = og_site_name['content'].strip()
    else:
        # Fallback: extract from title (before " - " or " | ")
        if features["title"]:
            for sep in [' - ', ' | ', ' – ']:
                if sep in features["title"]:
                    features["company_name"] = features["title"].split(sep)[0].strip()
                    break
            if not features["company_name"]:
                features["company_name"] = features["title"]

    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        features["description"] = meta_desc['content'].strip()

    # Extract emails (regex)
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, html)
    # Filter out common noise
    valid_emails = [e for e in emails if not any(x in e.lower() for x in ['example.com', 'sentry.io', 'google', 'facebook.com'])]
    features["emails"] = list(set(valid_emails[:5]))  # Max 5 unique

    # Extract social media links
    social_patterns = {
        'instagram': r'instagram\.com/([a-zA-Z0-9_.]+)',
        'facebook': r'facebook\.com/([a-zA-Z0-9_.]+)',
        'twitter': r'twitter\.com/([a-zA-Z0-9_]+)',
        'linkedin': r'linkedin\.com/company/([a-zA-Z0-9_-]+)',
        'youtube': r'youtube\.com/(@?[a-zA-Z0-9_-]+)'
    }

    for platform, pattern in social_patterns.items():
        matches = re.findall(pattern, html)
        if matches:
            # Take first valid match (not generic like "share")
            for match in matches:
                if match.lower() not in ['share', 'sharer', 'intent', 'plugins']:
                    features["social"][platform] = match
                    break

    return features


def extract_homepage_features_openai(html: str, domain: str) -> Dict:
    """
    Extract homepage features using OPENAI (accurate, costs ~$0.0001).

    Returns same format as regex version.
    """
    import openai

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[WARNING] OPENAI_API_KEY not set, falling back to regex")
        return extract_homepage_features_regex(html, domain)

    # Parse with BeautifulSoup to get text content
    soup = BeautifulSoup(html, 'html.parser')

    # Remove scripts and styles
    for script in soup(["script", "style"]):
        script.decompose()

    text_content = soup.get_text()
    # Limit to first 2000 chars to save tokens
    text_content = text_content[:2000]

    prompt = f"""Extract company information from this website homepage for domain: {domain}

Website content:
{text_content}

Return JSON with this exact schema:
{{
  "company_name": "Full company name",
  "title": "Website title",
  "description": "Brief description of what they do",
  "emails": ["email1@domain.com", "email2@domain.com"],
  "social": {{
    "instagram": "username",
    "facebook": "username",
    "twitter": "username",
    "linkedin": "company-name"
  }}
}}

IMPORTANT: Only include fields if you find them. Return empty strings/arrays if not found."""

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0
        )
        result = json.loads(response.choices[0].message.content.strip())
        return result
    except Exception as e:
        print(f"[WARNING] OpenAI extraction failed: {e}, falling back to regex")
        return extract_homepage_features_regex(html, domain)


def extract_homepage_features(html: str, domain: str, method: str = "regex") -> Dict:
    """
    Extract homepage features using specified method.

    Args:
        html: Homepage HTML content
        domain: Domain name
        method: "regex" (fast, free) or "openai" (accurate, ~$0.0001)
    """
    if method == "openai":
        return extract_homepage_features_openai(html, domain)
    else:
        return extract_homepage_features_regex(html, domain)


# ============================================================================
# Homepage Comparison
# ============================================================================

def fuzzy_match(s1: str, s2: str) -> float:
    """Return similarity score 0.0-1.0 using edit distance."""
    if not s1 or not s2:
        return 0.0

    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    if s1 == s2:
        return 1.0

    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 0.0

    distance = levenshtein_distance(s1, s2)
    similarity = 1.0 - (distance / max_len)

    return max(0.0, similarity)


def text_similarity(text1: str, text2: str) -> float:
    """Simple Jaccard similarity for text."""
    if not text1 or not text2:
        return 0.0

    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union) if union else 0.0


def email_domains_match(emails1: List[str], emails2: List[str]) -> bool:
    """Check if any email domains match."""
    if not emails1 or not emails2:
        return False

    domains1 = {e.split('@')[1].lower() for e in emails1 if '@' in e}
    domains2 = {e.split('@')[1].lower() for e in emails2 if '@' in e}

    return bool(domains1.intersection(domains2))


def count_matching_socials(social1: Dict, social2: Dict) -> int:
    """Count how many social media platforms match."""
    if not social1 or not social2:
        return 0

    count = 0
    for platform in social1:
        if platform in social2:
            # Normalize and compare
            user1 = social1[platform].lower().strip().replace('@', '')
            user2 = social2[platform].lower().strip().replace('@', '')
            if user1 == user2:
                count += 1

    return count


def compare_homepages(new_features: Dict, existing_features: Dict) -> float:
    """
    Compare homepage features and return similarity score 0.0-0.60 (60% weight).

    Breakdown:
        - Company name: 25%
        - Email domain: 15%
        - Meta description: 10%
        - Title: 5%
        - Social media: 5%
    """
    score = 0.0

    # Company name similarity (25%)
    company_sim = fuzzy_match(
        new_features.get("company_name", ""),
        existing_features.get("company_name", "")
    )
    score += 0.25 * company_sim

    # Email domain match (15%)
    if email_domains_match(
        new_features.get("emails", []),
        existing_features.get("emails", [])
    ):
        score += 0.15

    # Meta description similarity (10%)
    desc_sim = text_similarity(
        new_features.get("description", ""),
        existing_features.get("description", "")
    )
    score += 0.10 * desc_sim

    # Title similarity (5%)
    title_sim = fuzzy_match(
        new_features.get("title", ""),
        existing_features.get("title", "")
    )
    score += 0.05 * title_sim

    # Social media overlap (5%)
    social_matches = count_matching_socials(
        new_features.get("social", {}),
        existing_features.get("social", {})
    )
    score += 0.05 * min(social_matches / 3.0, 1.0)  # Max 3 platforms

    return score


# ============================================================================
# Main Deduplication Function
# ============================================================================

async def check_before_crawl(
    domain: str,
    pattern_threshold: float = 0.20,
    duplicate_threshold: float = 0.70,
    extraction_method: str = "regex"
) -> Dict:
    """
    Check if domain is duplicate BEFORE crawling.
    CLOUD-SAFE: Uses MongoDB only.

    Args:
        domain: Domain to check
        pattern_threshold: Minimum pattern score to trigger homepage check (default: 0.20)
        duplicate_threshold: Minimum total score to mark as duplicate (default: 0.70)
        extraction_method: "regex" (fast, free) or "openai" (accurate, ~$0.0001)

    Returns:
        {
            "status": "UNIQUE" | "DUPLICATE",
            "action": "crawl" | "skip",
            "primary_domain": str (if duplicate),
            "scores": {
                "pattern": float,
                "homepage": float,
                "total": float
            },
            "evidence": {...}
        }
    """
    # Get already crawled domains from MongoDB
    already_crawled = await get_crawled_domains()

    if not already_crawled:
        return {
            "status": "UNIQUE",
            "action": "crawl",
            "reason": "First domain to be crawled"
        }

    # Step 1: Pattern matching
    pattern_matches = find_pattern_matches(domain, already_crawled, pattern_threshold)

    if not pattern_matches:
        return {
            "status": "UNIQUE",
            "action": "crawl",
            "reason": "No pattern matches found"
        }

    print(f"[DEDUP] {domain} - Found {len(pattern_matches)} pattern matches, checking homepage...")

    # Step 2: Fetch homepage
    homepage_html = fetch_homepage(domain)

    if not homepage_html:
        return {
            "status": "UNIQUE",
            "action": "crawl",
            "reason": "Could not fetch homepage for comparison"
        }

    # Step 3: Extract features from new domain's homepage
    new_features = extract_homepage_features(homepage_html, domain, method=extraction_method)

    # Step 4: Compare with each pattern-matched candidate
    best_match = None
    best_total_score = 0.0
    best_scores = {}

    for candidate_domain, pattern_score in pattern_matches.items():
        # Load cached features for candidate from MongoDB
        candidate_features = await load_homepage_features(candidate_domain)

        if not candidate_features:
            # If features not cached, fetch and extract
            candidate_html = fetch_homepage(candidate_domain)
            if candidate_html:
                candidate_features = extract_homepage_features(candidate_html, candidate_domain, method=extraction_method)
                await save_homepage_features(candidate_domain, candidate_features)
            else:
                continue

        # Compare homepages
        homepage_score = compare_homepages(new_features, candidate_features)
        total_score = pattern_score + homepage_score

        if total_score > best_total_score:
            best_total_score = total_score
            best_match = candidate_domain
            best_scores = {
                "pattern": pattern_score,
                "homepage": homepage_score,
                "total": total_score
            }

    # Step 5: Decision
    result = {
        "domain": domain,
        "checked_at": datetime.utcnow(),
        "scores": best_scores,
        "evidence": {
            "new_company_name": new_features.get("company_name"),
            "new_emails": new_features.get("emails", []),
            "new_social": new_features.get("social", {})
        }
    }

    if best_total_score >= duplicate_threshold:
        result.update({
            "status": "DUPLICATE",
            "action": "skip",
            "primary_domain": best_match
        })

        # Save to MongoDB
        await save_dedup_result(result)

        print(f"[DUPLICATE] {domain} → {best_match} (score: {best_total_score:.0%})")
    else:
        result.update({
            "status": "UNIQUE",
            "action": "crawl"
        })

        # Cache homepage features for future comparisons in MongoDB
        await save_homepage_features(domain, new_features)

        print(f"[UNIQUE] {domain} (best match: {best_match} at {best_total_score:.0%}, below threshold)")

    return result
