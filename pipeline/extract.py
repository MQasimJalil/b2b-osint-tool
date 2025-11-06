import os
import json
import gzip
import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime

import openai
from openai import AsyncOpenAI
import dotenv

dotenv.load_dotenv()

# Rate limit handling
MAX_CONCURRENT_API_CALLS = 6  # Process max 6 chunks simultaneously to avoid rate limits


async def _retry_with_backoff(coro, max_retries: int = 5, domain: str = ""):
    """
    Retry async function with exponential backoff for rate limit errors (429).
    Parses OpenAI's suggested wait time from error message.
    """
    for attempt in range(max_retries):
        try:
            return await coro
        except Exception as e:
            error_str = str(e)
            
            # Check if it's a rate limit error (429)
            if "429" in error_str or "rate_limit_exceeded" in error_str:
                # Try to extract wait time from error message
                # Example: "Please try again in 3.685s"
                wait_time = 1.0  # default
                if "try again in" in error_str:
                    try:
                        parts = error_str.split("try again in")[1].split("s")[0].strip()
                        # Remove any non-numeric chars except dot
                        parts = ''.join(c for c in parts if c.isdigit() or c == '.')
                        wait_time = float(parts)
                    except:
                        wait_time = 2 ** attempt  # exponential fallback
                else:
                    wait_time = 2 ** attempt  # exponential: 1, 2, 4, 8, 16 seconds
                
                if attempt < max_retries - 1:
                    print(f"[{domain}] Rate limit hit, waiting {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[{domain}] Max retries reached for rate limit")
                    raise
            else:
                # Non-rate-limit error, raise immediately
                raise
    
    return None


def _get_client() -> openai.OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return openai.OpenAI(api_key=api_key)

def _get_async_client() -> AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=api_key)


def _read_crawled_pages(domain: str, output_dir: str = "crawled_data", char_limit: int = 500000) -> List[Dict]:
    """Load crawled pages for a domain (increased limit for better extraction)"""
    host = domain.replace(':', '_')
    path = os.path.join(output_dir, "domains", f"{host}.jsonl.gz")
    
    pages = []
    total_chars = 0
    
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                    content = row.get("content", "")
                    if total_chars + len(content) > char_limit:
                        break
                    pages.append(row)
                    total_chars += len(content)
                except Exception:
                    continue
    except FileNotFoundError:
        return []
    
    return pages


def _chunk_pages(pages: List[Dict], chars_per_chunk: int = 60000) -> List[str]:
    """
    Split pages into chunks for multi-pass extraction.
    IMPORTANT: Each page goes into ONLY ONE chunk to avoid duplicate API calls.
    """
    chunks = []
    current_chunk = []
    current_chars = 0
    
    for p in pages:
        page_text = f"# {p.get('title', 'Page')}\nURL: {p.get('url', '')}\n\n{p.get('content', '')}\n\n---\n\n"
        page_len = len(page_text)
        
        # If adding this page exceeds limit AND we have content, finalize current chunk
        if current_chars + page_len > chars_per_chunk and current_chunk:
            chunks.append("".join(current_chunk))
            current_chunk = []
            current_chars = 0
        
        # Add page to current chunk (even if it's large by itself)
        current_chunk.append(page_text)
        current_chars += page_len
    
    # Add remaining
    if current_chunk:
        chunks.append("".join(current_chunk))
    
    return chunks


async def _extract_profile_from_chunk(client: AsyncOpenAI, domain: str, chunk: str) -> Dict:
    """Extract company profile from a single chunk"""
    prompt = f"""Extract company profile and SMYKM (Show Me You Know Me) information from this website content.

CRITICAL INSTRUCTIONS:
1. Search VERY carefully for ALL contact information - emails, phones, addresses, social media links
2. Look for emails [DO NOT MISS ANY '*@*.*' IF you think it is an email address] in text like "contact@", "info@", "sales@", "@outlook.com", "@gmail.com", "@companyname.com" etc.
3. Extract social media URLs from links (instagram.com, facebook.com, linkedin.com, twitter.com, etc.)
4. SMYKM notes should be specific, factual insights that show you researched the company

Return JSON with this exact schema:
{{
  "domain": "{domain}",
  "company": "Full company name",
  "description": "Detailed description of what they sell and their business",
  "smykm_notes": [
    "Specific fact about their business that shows research",
    "Unique value proposition or differentiator",
    "Recent achievement, award, or milestone mentioned",
    "Company culture or values mentioned"
  ],
  "main_contacts": {{
    "email": ["contact@example.com", "sales@example.com", "any@email.found"],
    "phone": ["+1-555-0100"],
    "address": ["Full address if found"],
    "contact_page": "https://example.com/contact"
  }},
  "social_media": {{
    "linkedin": "https://linkedin.com/company/...",
    "instagram": "https://instagram.com/...",
    "twitter": "https://twitter.com/...",
    "facebook": "https://facebook.com/...",
    "youtube": "",
    "tiktok": ""
  }}
}}

VERYIMPORTANT: Extract EVERY email address you see in the content!

CONTENT:
{chunk}
"""
    
    # Don't catch exceptions here - let them bubble up to retry wrapper
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(resp.choices[0].message.content.strip())


def _merge_profiles(results: List[Dict], domain: str) -> Dict:
    """Merge multiple profile extractions (like text_processing2.py merge_results)"""
    merged = {
        "domain": domain,
        "company": "",
        "description": "",
        "smykm_notes": [],
        "main_contacts": {
            "email": [],
            "phone": [],
            "address": [],
            "contact_page": ""
        },
        "social_media": {
            "linkedin": "",
            "instagram": "",
            "twitter": "",
            "facebook": "",
            "youtube": "",
            "tiktok": ""
        }
    }
    
    best_desc_len = 0
    seen_smykm = set()
    
    for r in results:
        if not r:
            continue
        
        # Company name - prefer longest
        if len(r.get("company", "")) > len(merged["company"]):
            merged["company"] = r["company"]
        
        # Description - prefer longest/most detailed
        desc = r.get("description", "")
        if len(desc) > best_desc_len:
            merged["description"] = desc
            best_desc_len = len(desc)
        
        # SMYKM notes - deduplicate and merge
        for note in r.get("smykm_notes", []):
            if note and note not in seen_smykm:
                merged["smykm_notes"].append(note)
                seen_smykm.add(note)
        
        # Contacts - merge all unique values
        contacts = r.get("main_contacts", {}) or {}
        for email in contacts.get("email", []):
            if email and email not in merged["main_contacts"]["email"]:
                merged["main_contacts"]["email"].append(email)
        for phone in contacts.get("phone", []):
            if phone and phone not in merged["main_contacts"]["phone"]:
                merged["main_contacts"]["phone"].append(phone)
        for addr in contacts.get("address", []):
            if addr and addr not in merged["main_contacts"]["address"]:
                merged["main_contacts"]["address"].append(addr)
        if contacts.get("contact_page") and not merged["main_contacts"]["contact_page"]:
            merged["main_contacts"]["contact_page"] = contacts["contact_page"]
        
        # Social media - prefer first non-empty
        social = r.get("social_media", {}) or {}
        for platform in ["linkedin", "instagram", "twitter", "facebook", "youtube", "tiktok"]:
            if social.get(platform) and not merged["social_media"][platform]:
                merged["social_media"][platform] = social[platform]
    
    return merged


def extract_company_profile(domain: str, output_dir: str = "crawled_data") -> Optional[Dict]:
    """
    Extract company profile using multi-chunk strategy with proper async handling.
    Inspired by text_processing2.py for better quality and contact discovery.
    """
    pages = _read_crawled_pages(domain, output_dir, char_limit=500000)
    
    if not pages:
        return None
    
    # Prioritize contact/about pages
    priority_pages = []
    other_pages = []
    
    for p in pages:
        url_lower = p.get("url", "").lower()
        if any(kw in url_lower for kw in ["/about", "/contact", "/team", "/company", "/who-we-are"]) or p.get("depth", 0) == 0:
            priority_pages.append(p)
        else:
            other_pages.append(p)
    
    # Use priority pages first, then others
    ordered_pages = priority_pages + other_pages
    chunks = _chunk_pages(ordered_pages, chars_per_chunk=60000)
    
    if not chunks:
        return None
    
    print(f"[{domain}] Processing {len(chunks)} chunks for company profile...")
    
    async def run_extraction():
        client = _get_async_client()
        try:
            # Use semaphore to limit concurrent API calls
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_API_CALLS)
            
            async def limited_extract(chunk):
                async with semaphore:
                    # Wrap in retry logic
                    return await _retry_with_backoff(
                        _extract_profile_from_chunk(client, domain, chunk),
                        max_retries=5,
                        domain=domain
                    )
            
            tasks = [limited_extract(chunk) for chunk in chunks]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and return valid results
            valid_results = []
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    print(f"[{domain}] Chunk {i+1}/{len(chunks)} failed: {r}")
                elif r:
                    valid_results.append(r)
            
            return valid_results
        finally:
            # Properly close the client to avoid event loop errors
            await client.close()
    
    try:
        # Create new event loop to avoid "Event loop is closed" error
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(run_extraction())
        finally:
            loop.close()
        
        merged = _merge_profiles(results, domain)
        merged["extracted_at"] = datetime.utcnow().isoformat() + "Z"
        merged["crawled_pages"] = len(pages)
        merged["chunks_processed"] = len(chunks)
        return merged
    except Exception as e:
        print(f"[{domain}] Company extraction error: {e}")
        return None


async def _extract_products_from_chunk(client: AsyncOpenAI, domain: str, chunk: str, industry_filter: str = "goalkeeper gloves") -> List[Dict]:
    """Extract products from a single chunk with industry filtering"""
    prompt = f"""Extract ONLY products related to: {industry_filter}

CRITICAL RULES:
1. IGNORE products NOT related to {industry_filter} (e.g., if looking for goalkeeper gloves, ignore general clothing, shoes, balls, training cones)
2. Only extract goalkeeper-specific equipment (gloves, jerseys, pants, training gear for goalkeepers)
3. Copy product descriptions EXACTLY as written on the website - do NOT add your own thoughts or explanations
4. Include product specs EXACTLY as shown (sizes, materials, cuts, etc.)
5. Extract customer reviews if available on the page - copy exact quotes

For each RELEVANT product found, return JSON in this format:
{{
  "brand": "Brand name if mentioned",
  "name": "Exact product name from website",
  "category": "Product category",
  "price": "Exact price as shown (e.g., $49.99, €35.00, Rs.14,600.00)",
  "specs": {{"key": "value as shown on site"}},
  "description": "EXACT product description from website - copy word-for-word, do not summarize or paraphrase",
  "image_url": "Product image URL if found",
  "url": "Product page URL",
  "reviews": ["Extract customer reviews if available - copy exact quotes from website", "Include both positive and negative reviews"]
}}

Return JSON with "products" key containing an array of ONLY relevant products.
If no relevant products found, return empty array.

IMPORTANT: Use EXACT text from the website, not your interpretation!

CONTENT:
{chunk}
"""
    
    # Don't catch exceptions here - let them bubble up to retry wrapper
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    data = json.loads(resp.choices[0].message.content.strip())
    
    # Handle both array and object with products key
    if isinstance(data, list):
        return data
    elif "products" in data:
        return data["products"]
    else:
        return []


def _merge_products(all_products: List[List[Dict]], domain: str) -> List[Dict]:
    """Deduplicate products from multiple chunks using name + price"""
    seen = set()
    merged = []
    
    for product_list in all_products:
        # Skip None or non-list entries
        if not product_list or not isinstance(product_list, list):
            continue
            
        for p in product_list:
            # Skip None or non-dict entries
            if not p or not isinstance(p, dict):
                continue
            
            # Safely get values with None checks
            name = p.get("name")
            price = p.get("price")
            url = p.get("url")
            
            # Convert to strings safely
            name = name.lower().strip() if name else ""
            price = price.lower().strip() if price else ""
            url = url.strip() if url else ""
            
            # Create dedup key: use (name, price) as primary, URL as fallback
            if name and price:
                key = (name, price)
            elif name and url:
                key = (name, url)
            elif name:
                key = (name, "no_price")
            else:
                continue  # Skip products without name
            
            if key not in seen:
                seen.add(key)
                p["domain"] = domain
                merged.append(p)
    
    # Add product IDs
    for i, p in enumerate(merged):
        p["product_id"] = f"{domain}_p{i+1}"
    
    # Calculate total safely
    total_count = sum(len(pl) for pl in all_products if pl and isinstance(pl, list))
    print(f"[{domain}] Deduplication: {total_count} total → {len(merged)} unique products")
    
    return merged


def extract_products(domain: str, output_dir: str = "crawled_data", industry: str = "goalkeeper gloves") -> List[Dict]:
    """
    Extract product catalog using multi-chunk async strategy with industry filtering.
    Processes more content for better product discovery.
    
    Args:
        domain: Domain to extract products from
        output_dir: Directory containing crawled data
        industry: Industry filter to only extract relevant products (e.g., "goalkeeper gloves")
    """
    pages = _read_crawled_pages(domain, output_dir, char_limit=500000)
    
    if not pages:
        return []
    
    # Prioritize product/shop pages
    product_pages = []
    other_pages = []
    
    for p in pages:
        url_lower = p.get("url", "").lower()
        if any(kw in url_lower for kw in ["/product", "/shop", "/collection", "/catalog", "/store", "/glove"]):
            product_pages.append(p)
        else:
            other_pages.append(p)
    
    # Use product pages first, then others if not enough
    ordered_pages = product_pages + other_pages
    chunks = _chunk_pages(ordered_pages, chars_per_chunk=50000)
    
    if not chunks:
        return []
    
    print(f"[{domain}] Processing {len(chunks)} chunks for {industry} products...")
    
    async def run_extraction():
        client = _get_async_client()
        try:
            # Use semaphore to limit concurrent API calls
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_API_CALLS)
            
            async def limited_extract(chunk):
                async with semaphore:
                    # Wrap in retry logic
                    return await _retry_with_backoff(
                        _extract_products_from_chunk(client, domain, chunk, industry),
                        max_retries=5,
                        domain=domain
                    )
            
            tasks = [limited_extract(chunk) for chunk in chunks]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and return valid results
            valid_results = []
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    print(f"[{domain}] Product chunk {i+1}/{len(chunks)} failed: {r}")
                elif r:
                    valid_results.append(r)
            
            return valid_results
        finally:
            # Properly close the client to avoid event loop errors
            await client.close()
    
    try:
        # Create new event loop to avoid "Event loop is closed" error
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            all_products = loop.run_until_complete(run_extraction())
        finally:
            loop.close()
        
        merged = _merge_products(all_products, domain)
        print(f"[{domain}] Extracted {len(merged)} relevant {industry} products (filtered out unrelated items)")
        return merged
    except Exception as e:
        print(f"[{domain}] Product extraction error: {e}")
        return []


def save_company_data(domain: str, company_profile: Dict, products: List[Dict], base_dir: str = "extracted_data"):
    """Save company profile and products to per-domain folder"""
    domain_dir = os.path.join(base_dir, "companies", domain)
    os.makedirs(domain_dir, exist_ok=True)
    
    # Save company profile
    with open(os.path.join(domain_dir, "profile.json"), 'w', encoding='utf-8') as f:
        json.dump(company_profile, f, ensure_ascii=False, indent=2)
    
    # Save products
    with open(os.path.join(domain_dir, "products.jsonl"), 'w', encoding='utf-8') as f:
        for p in products:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    
    # Save metadata
    metadata = {
        "domain": domain,
        "extraction_date": datetime.utcnow().isoformat() + "Z",
        "products_extracted": len(products),
        "crawled_pages": company_profile.get("crawled_pages", 0)
    }
    with open(os.path.join(domain_dir, "metadata.json"), 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    print(f"[{domain}] Saved: company profile + {len(products)} products")


def build_global_indexes(base_dir: str = "extracted_data"):
    """Build global indexes from per-domain data"""
    companies_dir = os.path.join(base_dir, "companies")
    indexes_dir = os.path.join(base_dir, "indexes")
    os.makedirs(indexes_dir, exist_ok=True)
    
    if not os.path.exists(companies_dir):
        return
    
    companies = []
    products = []
    
    for domain in os.listdir(companies_dir):
        domain_path = os.path.join(companies_dir, domain)
        if not os.path.isdir(domain_path):
            continue
        
        # Load company
        company_file = os.path.join(domain_path, "profile.json")
        if os.path.exists(company_file):
            try:
                with open(company_file, 'r', encoding='utf-8') as f:
                    company = json.load(f)
                    # Simplified for index
                    companies.append({
                        "domain": domain,
                        "company": company.get("company", ""),
                        "email": (company.get("main_contacts", {}) or {}).get("email", []),
                        "products_count": 0  # will update below
                    })
            except Exception:
                pass
        
        # Load products
        products_file = os.path.join(domain_path, "products.jsonl")
        if os.path.exists(products_file):
            try:
                domain_products = 0
                with open(products_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            p = json.loads(line)
                            products.append({
                                "domain": domain,
                                "product_id": p.get("product_id", ""),
                                "brand": p.get("brand", ""),
                                "name": p.get("name", ""),
                                "category": p.get("category", ""),
                                "price": p.get("price", ""),
                                "url": p.get("url", "")
                            })
                            domain_products += 1
                        except Exception:
                            continue
                # Update product count
                if companies:
                    companies[-1]["products_count"] = domain_products
            except Exception:
                pass
    
    # Write global indexes
    with open(os.path.join(indexes_dir, "all_companies.jsonl"), 'w', encoding='utf-8') as f:
        for c in companies:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    
    with open(os.path.join(indexes_dir, "all_products.jsonl"), 'w', encoding='utf-8') as f:
        for p in products:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    
    print(f"Built global indexes: {len(companies)} companies, {len(products)} products")


def get_company_data(domain: str, base_dir: str = "extracted_data") -> Optional[Dict]:
    """Helper: Get all data for one company (for email generation)"""
    domain_path = os.path.join(base_dir, "companies", domain)
    
    if not os.path.exists(domain_path):
        return None
    
    result = {"domain": domain}
    
    # Load company
    company_file = os.path.join(domain_path, "profile.json")
    if os.path.exists(company_file):
        with open(company_file, 'r', encoding='utf-8') as f:
            result["company"] = json.load(f)
    
    # Load products
    products_file = os.path.join(domain_path, "products.jsonl")
    if os.path.exists(products_file):
        products = []
        with open(products_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    products.append(json.loads(line))
                except Exception:
                    continue
        result["products"] = products
    
    # Load metadata
    metadata_file = os.path.join(domain_path, "metadata.json")
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r', encoding='utf-8') as f:
            result["metadata"] = json.load(f)
    
    return result
