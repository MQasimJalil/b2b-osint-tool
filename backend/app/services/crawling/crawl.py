import os
import sys
import gzip
import json
import time
import asyncio
import random
import hashlib
from typing import List, Dict, Set, Tuple, Optional
from urllib.parse import urlparse, urljoin, urldefrag
from urllib import robotparser

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from tqdm import tqdm

# Add backend to path for MongoDB imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# MongoDB repository imports
from app.db.repositories.crawling_repo import (
    # Sync versions (for non-async code)
    get_crawl_state_sync,
    update_crawl_state_sync,
    get_visited_urls_sync,
    get_content_hashes_sync,
    is_domain_crawled_sync,
    get_crawl_status_batch_sync,
    mark_crawl_complete_sync,
    save_crawled_page_sync,
    get_crawled_page_count_sync,
    # Async versions (for async code)
    get_visited_urls,
    get_content_hashes,
    save_crawled_page,
    update_crawl_state,
    mark_crawl_complete
)
from app.db.mongodb_session import init_db

# Note: deduplicate module needs to be created or these functions need to be implemented here
from app.services.crawling.deduplicate import (
    track_crawled_domain,
    save_homepage_features,
    extract_homepage_features,
    check_before_crawl
)

# Note: MongoDB initialization is handled at Celery worker startup
# via the celery_app worker_process_init signal. No need to initialize here.


SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff",
    ".svg", ".ico", ".zip", ".rar", ".7z", ".tar", ".gz", ".pdf"
}


def _host(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _canonical(u: str) -> str:
    u, _ = urldefrag(u)
    if u.endswith('/'):
        u = u.rstrip('/')
    return u


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _paths(out_dir: str, base_url: str):
    host = _host(base_url).replace(':', '_')
    domains_dir = os.path.join(out_dir, "domains")
    state_dir = os.path.join(out_dir, "crawl_state")
    os.makedirs(domains_dir, exist_ok=True)
    os.makedirs(state_dir, exist_ok=True)
    return (
        os.path.join(domains_dir, f"{host}.jsonl.gz"),
        os.path.join(state_dir, f"{host}_visited.txt"),
        os.path.join(state_dir, f"{host}_hashes.txt"),
        os.path.join(state_dir, f"{host}_complete.txt"),  # Completion marker
    )


def is_domain_fully_crawled(domain: str, output_dir: str = None, min_pages: int = 5) -> bool:
    """
    DEPRECATED: Check if domain has been crawled (filesystem-based).

    This function is deprecated. Use MongoDB-based crawling functions instead.
    Kept for backward compatibility.
    """
    print("WARNING: is_domain_fully_crawled is deprecated. Use MongoDB-based functions instead.")
    return False  # Always return False to force re-crawl


def _is_domain_fully_crawled_legacy(domain: str, output_dir: str = "crawled_data", min_pages: int = 5) -> bool:
    """LEGACY: Filesystem-based implementation (deprecated)"""
    """
    Check if a domain has been FULLY crawled (completion marker exists).
    Returns True only if the crawl completed successfully.
    Partially crawled domains (interrupted mid-way) will return False.
    """
    try:
        # Try MongoDB first
        return is_domain_crawled_sync(domain)
    except Exception as e:
        print(f"Warning: Failed to check MongoDB for {domain}: {e}")
        # Fallback to file-based check
        base_url = f"https://{domain}"
        out_path, visited_path, hashes_path, complete_path = _paths(output_dir, base_url)

        # Only consider domain "fully crawled" if completion marker exists
        if os.path.exists(complete_path):
            return True

        return False


def get_crawl_status(domains: List[str], output_dir: str = None) -> Dict[str, Dict]:
    """
    DEPRECATED: Get crawl status for multiple domains (filesystem-based).

    This function is deprecated. Use get_crawl_status_batch_sync from crawling_repo instead.
    Kept for backward compatibility.
    """
    print("WARNING: get_crawl_status is deprecated. Use get_crawl_status_batch_sync instead.")
    return {domain: {"fully_crawled": False, "pages": 0} for domain in domains}


def _get_crawl_status_legacy(domains: List[str], output_dir: str = "crawled_data") -> Dict[str, Dict]:
    """LEGACY: Filesystem-based implementation (deprecated)"""
    """
    Get crawl status for a list of domains.
    Returns dict with domain -> {fully_crawled: bool, pages: int, visited_urls: int, in_progress: bool}
    """
    try:
        # Try MongoDB first
        return get_crawl_status_batch_sync(domains)
    except Exception as e:
        print(f"Warning: Failed to get crawl status from MongoDB: {e}")
        # Fallback to file-based status check
        status = {}
        for domain in domains:
            base_url = f"https://{domain}"
            out_path, visited_path, hashes_path, complete_path = _paths(output_dir, base_url)

            pages = 0
            visited = 0
            fully_crawled = os.path.exists(complete_path)

            if os.path.exists(out_path):
                try:
                    with gzip.open(out_path, 'rt', encoding='utf-8') as f:
                        pages = sum(1 for _ in f)
                except Exception:
                    pass

            if os.path.exists(visited_path):
                visited = len(_load_set(visited_path))

            # In-progress = has some data but no completion marker
            in_progress = (pages > 0 or visited > 0) and not fully_crawled

            status[domain] = {
                "fully_crawled": fully_crawled,
                "pages": pages,
                "visited_urls": visited,
                "in_progress": in_progress
            }

        return status


def _load_set(path: str) -> Set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _save_set(path: str, data: Set[str]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for item in data:
            f.write(item + "\n")
    os.replace(tmp, path)


async def _fetch_page(crawler, url: str, depth: int, host: str) -> Optional[Dict]:
    """Fetch a single page and return parsed result."""
    try:
        cfg = CrawlerRunConfig(
            excluded_tags=[] if depth == 0 else ['form', 'header', 'footer', 'nav'],
            css_selector="body",
            exclude_external_links=True,
            exclude_external_images=True,
        )
        res = await crawler.arun(url, config=cfg)
        
        text = (res.markdown or "").strip()
        if not text:
            return None
        
        return {
            "url": url,
            "domain": host,
            "title": getattr(res, 'title', None),
            "content": text,
            "content_hash": _sha256_text(text),
            "depth": depth,
            "ts": int(time.time()),
            "links": res.links.get("internal", []) if res.links else []
        }
    except Exception:
        return None


async def _crawl_one(base_url: str, out_path: str, visited_path: str, hashes_path: str,
                     complete_path: str, max_pages: int = 200, max_depth: int = 2,
                     retry_on_zero: bool = True, pbar: Optional[tqdm] = None, concurrency: int = 5):
    """
    Crawl a single domain with concurrent page fetching.
    Resumes from existing state if crawl was interrupted.
    Writes completion marker only when crawl finishes successfully.
    Uses MongoDB for state management with file-based fallback.

    Args:
        concurrency: Number of pages to fetch in parallel (default: 5)
    """
    host = _host(base_url)
    use_mongodb = False

    # Try to load state from MongoDB first
    try:
        visited = set(get_visited_urls_sync(host))  # Convert to set
        content_hashes = set(get_content_hashes_sync(host))  # Convert to set
        use_mongodb = True
        if pbar:
            pbar.write(f"[{host}] Using MongoDB for state management")
    except Exception as e:
        if pbar:
            pbar.write(f"[{host}] MongoDB unavailable, falling back to files: {e}")
        # Fallback to file-based state
        visited = _load_set(visited_path)
        content_hashes = _load_set(hashes_path)

    queue: List[Tuple[str, int]] = [(base_url, 0)] if base_url not in visited else []
    robots: Optional[robotparser.RobotFileParser] = None
    
    # Load robots.txt
    try:
        rp = robotparser.RobotFileParser()
        root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
        rp.set_url(urljoin(root, "/robots.txt"))
        rp.read()
        robots = rp
    except Exception:
        pass

    attempt = 0
    max_attempts = 2 if retry_on_zero else 1
    
    while attempt < max_attempts:
        pages_found = 0
        attempt += 1
        
        async with AsyncWebCrawler() as crawler:
            while queue and len(visited) < max_pages:
                # Prepare batch of URLs to fetch concurrently
                batch = []
                while queue and len(batch) < concurrency and len(visited) + len(batch) < max_pages:
                    url, depth = queue.pop(0)
                    url = _canonical(url)
                    
                    # Skip if already visited
                    if url in visited:
                        continue
                    
                    # Skip unwanted extensions
                    parsed = urlparse(url)
                    if os.path.splitext(parsed.path.lower())[1] in SKIP_EXTENSIONS:
                        continue
                    
                    # Check robots.txt
                    if robots and not robots.can_fetch("*", url):
                        continue
                    
                    # Add to batch
                    batch.append((url, depth))
                    visited.add(url)
                
                if not batch:
                    break
                
                # Fetch pages concurrently
                tasks = [_fetch_page(crawler, url, depth, host) for url, depth in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for (url, depth), result in zip(batch, results):
                    if isinstance(result, Exception) or result is None:
                        continue

                    h = result["content_hash"]
                    if h not in content_hashes:
                        content_hashes.add(h)
                        pages_found += 1

                        # Save page to MongoDB and/or file
                        if use_mongodb:
                            try:
                                save_crawled_page_sync(
                                    domain=host,
                                    url=result["url"],
                                    title=result.get("title"),
                                    content=result["content"],
                                    content_hash=result["content_hash"],
                                    depth=result["depth"],
                                    links=result.get("links", [])
                                )
                            except Exception as e:
                                if pbar:
                                    pbar.write(f"[{host}] Warning: Failed to save page to MongoDB: {e}")
                                # Fallback to file
                                use_mongodb = False

                        # Always save to file as backup
                        row = {k: v for k, v in result.items() if k != "links"}
                        with gzip.open(out_path, 'at', encoding='utf-8') as f:
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    
                    # Extract links for next depth
                    if depth < max_depth:
                        for link in result.get("links", []):
                            href = link.get('href')
                            if not href:
                                continue
                            nxt = _canonical(urljoin(url, href))
                            if _host(nxt) != host:
                                continue
                            if nxt not in visited:
                                queue.append((nxt, depth + 1))
                
                # Save state after every batch (crash-safe!)
                if use_mongodb:
                    try:
                        update_crawl_state_sync(
                            domain=host,
                            visited_urls=list(visited),
                            content_hashes=list(content_hashes),
                            is_complete=False,
                            pages_crawled=len(content_hashes)
                        )
                    except Exception as e:
                        if pbar:
                            pbar.write(f"[{host}] Warning: Failed to update MongoDB state: {e}")
                        use_mongodb = False

                # Always save to file as backup
                _save_set(visited_path, visited)
                _save_set(hashes_path, content_hashes)
                
                # Polite delay between batches
                await asyncio.sleep(random.uniform(0.2, 0.5))
        
        # Save final state
        if use_mongodb:
            try:
                update_crawl_state_sync(
                    domain=host,
                    visited_urls=list(visited),
                    content_hashes=list(content_hashes),
                    is_complete=False,
                    pages_crawled=len(content_hashes)
                )
            except Exception as e:
                if pbar:
                    pbar.write(f"[{host}] Warning: Failed to save final state to MongoDB: {e}")

        # Always save to file as backup
        _save_set(visited_path, visited)
        _save_set(hashes_path, content_hashes)

    # Mark crawl as complete in MongoDB and file
    if use_mongodb:
        try:
            mark_crawl_complete_sync(host, len(visited), len(content_hashes))
            if pbar:
                pbar.write(f"[{host}] Marked as complete in MongoDB")
        except Exception as e:
            if pbar:
                pbar.write(f"[{host}] Warning: Failed to mark complete in MongoDB: {e}")

    # Write completion marker file
    with open(complete_path, 'w', encoding='utf-8') as f:
        f.write(f"Completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total URLs visited: {len(visited)}\n")
        f.write(f"Unique pages: {len(content_hashes)}\n")

    # Track this domain as crawled for deduplication (if deduplicate module exists)
    try:
        from app.services.crawling.deduplicate import track_crawled_domain, save_homepage_features, extract_homepage_features
        track_crawled_domain(host)

        # Extract and cache homepage features for future deduplication
        try:
            # Find homepage in crawled pages
            homepage_url = base_url
            # Read from crawled data to extract homepage
            with gzip.open(out_path, 'rt', encoding='utf-8') as f:
                for line in f:
                    try:
                        page = json.loads(line)
                        if page.get('depth') == 0:  # Homepage
                            # Create pseudo-HTML from content for feature extraction
                            html_content = f"<html><head><title>{page.get('title', '')}</title></head><body>{page.get('content', '')}</body></html>"
                            features = extract_homepage_features(html_content, host, method="regex")
                            save_homepage_features(host, features)
                            break
                    except:
                        continue
        except Exception:
            # Not critical if we can't extract features now, will fetch later if needed
            pass
    except ImportError:
        # Deduplicate module not available, skip this step
        pass

    if pbar:
        pbar.write(f"[{host}] ✓ COMPLETE: {len(visited)} URLs, {len(content_hashes)} unique pages")
        pbar.update(1)  # Mark this domain as complete
    else:
        print(f"[{host}] ✓ COMPLETE: {len(visited)} URLs, {len(content_hashes)} unique pages")


def crawl_domains(domains: List[str], output_dir: str = None, max_pages: int = 2000,
                  max_depth: int = 3, skip_crawled: bool = True, concurrency: int = 5,
                  max_parallel_domains: int = 3):
    """
    DEPRECATED: Crawl multiple domains (filesystem-based).

    This function is deprecated. Use crawl_domains_mongodb_only instead.
    Kept for backward compatibility but delegates to MongoDB version.

    Args:
        domains: List of domains to crawl
        output_dir: DEPRECATED (no longer used)
        max_pages: Max pages to crawl per domain
        max_depth: Max depth to crawl
        skip_crawled: If True, skip domains that already have sufficient crawled data
        concurrency: Number of pages to fetch concurrently per domain
        max_parallel_domains: Max domains to crawl simultaneously
    """
    print("WARNING: crawl_domains is deprecated. Using crawl_domains_mongodb_only instead.")
    import asyncio
    return asyncio.run(crawl_domains_mongodb_only(domains, max_pages, max_depth, skip_crawled, concurrency, max_parallel_domains))
    # Filter out already-crawled domains if requested
    if skip_crawled:
        to_crawl = [d for d in domains if not is_domain_fully_crawled(d, output_dir)]
        skipped = len(domains) - len(to_crawl)
        if skipped > 0:
            print(f"Skipping {skipped} already-crawled domains. Crawling {len(to_crawl)} remaining.")
    else:
        to_crawl = domains
    
    if not to_crawl:
        print("All domains already crawled!")
        return
    
    # Create progress bar
    pbar = tqdm(total=len(to_crawl), desc="Crawling domains", unit="domain")
    
    async def worker(queue: asyncio.Queue):
        """Worker that processes domains from the queue."""
        while True:
            try:
                domain = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check if queue is done
                if queue.empty():
                    break
                continue
            
            if domain is None:  # Poison pill
                break
            
            try:
                base = f"https://{domain}"
                out, visited, hashes, complete = _paths(output_dir, base)
                await _crawl_one(base, out, visited, hashes, complete, max_pages=max_pages, 
                               max_depth=max_depth, pbar=pbar, concurrency=concurrency)
            except Exception as e:
                pbar.write(f"[ERROR] Failed to crawl {domain}: {e}")
            finally:
                queue.task_done()
    
    async def runner():
        # Create queue and add all domains
        queue = asyncio.Queue()
        for domain in to_crawl:
            await queue.put(domain)
        
        # Start worker pool (max_parallel_domains workers)
        workers = [asyncio.create_task(worker(queue)) for _ in range(max_parallel_domains)]
        
        # Wait for all domains to be processed
        await queue.join()
        
        # Stop workers
        for _ in range(max_parallel_domains):
            await queue.put(None)  # Poison pill
        await asyncio.gather(*workers)

    # Handle both cases: running from async context (Streamlit) or sync context (main.py)
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
        # If we're here, there's a running loop (e.g., Streamlit)
        # We need to run in a separate thread with its own event loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, runner())
            future.result()  # Wait for completion
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        asyncio.run(runner())

    pbar.close()


async def _crawl_one_mongodb_only(base_url: str, max_pages: int = 200, max_depth: int = 2,
                                   retry_on_zero: bool = True, pbar: Optional[tqdm] = None, concurrency: int = 5) -> Dict[str, any]:
    """
    Crawl a single domain storing ONLY in MongoDB (no filesystem I/O).
    Resumes from existing state if crawl was interrupted.

    Args:
        base_url: Base URL to crawl (e.g., https://example.com)
        max_pages: Max pages to crawl
        max_depth: Max depth to crawl
        retry_on_zero: If True, retry once if no pages found
        pbar: Optional progress bar
        concurrency: Number of pages to fetch in parallel (default: 5)

    Returns:
        Dict with crawl statistics: {pages_crawled, urls_visited, domain, success}
    """
    # Ensure MongoDB is initialized in this event loop (called from parent, but safe to call again)
    try:
        await init_db()
        if pbar:
            pbar.write(f"[DEBUG] MongoDB initialized successfully in event loop")
    except Exception as e:
        if pbar:
            pbar.write(f"[ERROR] Failed to initialize MongoDB: {e}")
        raise

    host = _host(base_url)

    # Load state from MongoDB (using async versions)
    try:
        visited = set(await get_visited_urls(host))  # Convert to set
        content_hashes = set(await get_content_hashes(host))  # Convert to set
        if pbar:
            pbar.write(f"[{host}] Loaded state from MongoDB: {len(visited)} visited, {len(content_hashes)} unique pages")
    except Exception as e:
        if pbar:
            pbar.write(f"[{host}] Starting fresh crawl (MongoDB): {e}")
        visited = set()
        content_hashes = set()

    queue: List[Tuple[str, int]] = [(base_url, 0)] if base_url not in visited else []
    robots: Optional[robotparser.RobotFileParser] = None

    # Load robots.txt
    try:
        rp = robotparser.RobotFileParser()
        root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
        rp.set_url(urljoin(root, "/robots.txt"))
        rp.read()
        robots = rp
    except Exception:
        pass

    attempt = 0
    max_attempts = 2 if retry_on_zero else 1

    while attempt < max_attempts:
        pages_found = 0
        attempt += 1

        async with AsyncWebCrawler() as crawler:
            while queue and len(visited) < max_pages:
                # Prepare batch of URLs to fetch concurrently
                batch = []
                while queue and len(batch) < concurrency and len(visited) + len(batch) < max_pages:
                    url, depth = queue.pop(0)
                    url = _canonical(url)

                    # Skip if already visited
                    if url in visited:
                        continue

                    # Skip unwanted extensions
                    parsed = urlparse(url)
                    if os.path.splitext(parsed.path.lower())[1] in SKIP_EXTENSIONS:
                        continue

                    # Check robots.txt
                    if robots and not robots.can_fetch("*", url):
                        continue

                    # Add to batch
                    batch.append((url, depth))
                    visited.add(url)

                if not batch:
                    break

                # Fetch pages concurrently
                tasks = [_fetch_page(crawler, url, depth, host) for url, depth in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for (url, depth), result in zip(batch, results):
                    if isinstance(result, Exception) or result is None:
                        continue

                    h = result["content_hash"]
                    if h not in content_hashes:
                        content_hashes.add(h)
                        pages_found += 1

                        # Save page to MongoDB ONLY (using async version)
                        try:
                            await save_crawled_page(
                                domain=host,
                                url=result["url"],
                                title=result.get("title"),
                                content=result["content"],
                                content_hash=result["content_hash"],
                                depth=result["depth"],
                                links=result.get("links", [])
                            )
                        except Exception as e:
                            import traceback
                            if pbar:
                                pbar.write(f"[{host}] ERROR: Failed to save page to MongoDB: {e}")
                                pbar.write(f"[{host}] Traceback: {traceback.format_exc()}")
                            raise  # Fail fast if MongoDB is unavailable

                    # Extract links for next depth
                    if depth < max_depth:
                        for link in result.get("links", []):
                            href = link.get('href')
                            if not href:
                                continue
                            nxt = _canonical(urljoin(url, href))
                            if _host(nxt) != host:
                                continue
                            if nxt not in visited:
                                queue.append((nxt, depth + 1))

                # Save state after every batch (using async version)
                try:
                    await update_crawl_state(
                        domain=host,
                        visited_urls=list(visited),
                        content_hashes=list(content_hashes),
                        is_complete=False,
                        pages_crawled=len(content_hashes)
                    )
                except Exception as e:
                    if pbar:
                        pbar.write(f"[{host}] ERROR: Failed to update MongoDB state: {e}")
                    raise  # Fail fast if MongoDB is unavailable

                # Polite delay between batches
                await asyncio.sleep(random.uniform(0.2, 0.5))

        # Save final state (using async version)
        try:
            await update_crawl_state(
                domain=host,
                visited_urls=list(visited),
                content_hashes=list(content_hashes),
                is_complete=False,
                pages_crawled=len(content_hashes)
            )
        except Exception as e:
            if pbar:
                pbar.write(f"[{host}] ERROR: Failed to save final state to MongoDB: {e}")
            raise

    # Mark crawl as complete in MongoDB (using async version)
    try:
        await mark_crawl_complete(host, len(visited), len(content_hashes))
        if pbar:
            pbar.write(f"[{host}] ✓ COMPLETE: {len(visited)} URLs, {len(content_hashes)} unique pages (MongoDB only)")
    except Exception as e:
        if pbar:
            pbar.write(f"[{host}] ERROR: Failed to mark complete in MongoDB: {e}")
        raise

    if pbar:
        pbar.update(1)  # Mark this domain as complete

    return {
        "domain": host,
        "pages_crawled": len(content_hashes),
        "urls_visited": len(visited),
        "success": True
    }


async def crawl_domains_mongodb_only(
    domains: List[str],
    max_pages: int = 200,
    max_depth: int = 3,
    skip_crawled: bool = True,
    concurrency: int = 5,
    max_parallel_domains: int = 3
) -> Dict[str, any]:
    """
    Crawl multiple domains storing ONLY in MongoDB (no filesystem).

    This function removes all file I/O operations:
    - No gzip files
    - No visited_path, hashes_path, complete_path
    - Everything stored in MongoDB via save_crawled_page_sync()

    Args:
        domains: List of domains to crawl
        max_pages: Max pages to crawl per domain (default: 200)
        max_depth: Max depth to crawl (default: 3)
        skip_crawled: If True, skip domains already fully crawled
        concurrency: Number of pages to fetch concurrently per domain (default: 5)
        max_parallel_domains: Max domains to crawl simultaneously (default: 3)

    Returns:
        Dict with overall statistics:
        {
            "total_domains": int,
            "crawled_domains": int,
            "skipped_domains": int,
            "total_pages": int,
            "results": List[Dict]  # Per-domain results
        }
    """
    # Ensure MongoDB is initialized in this event loop
    await init_db()

    # Filter out already-crawled domains if requested
    if skip_crawled:
        to_crawl = [d for d in domains if not is_domain_fully_crawled(d)]
        skipped = len(domains) - len(to_crawl)
        if skipped > 0:
            print(f"Skipping {skipped} already-crawled domains. Crawling {len(to_crawl)} remaining.")
    else:
        to_crawl = domains

    if not to_crawl:
        print("All domains already crawled!")
        return {
            "total_domains": len(domains),
            "crawled_domains": 0,
            "skipped_domains": len(domains),
            "total_pages": 0,
            "results": []
        }

    # Create progress bar
    pbar = tqdm(total=len(to_crawl), desc="Crawling domains (MongoDB only)", unit="domain")

    results = []

    async def worker(queue: asyncio.Queue):
        """Worker that processes domains from the queue."""
        while True:
            try:
                domain = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if queue.empty():
                    break
                continue

            if domain is None:  # Poison pill
                break

            try:
                base = f"https://{domain}"
                result = await _crawl_one_mongodb_only(
                    base,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    pbar=pbar,
                    concurrency=concurrency
                )
                results.append(result)
            except Exception as e:
                pbar.write(f"[ERROR] Failed to crawl {domain}: {e}")
                results.append({
                    "domain": domain,
                    "pages_crawled": 0,
                    "urls_visited": 0,
                    "success": False,
                    "error": str(e)
                })
            finally:
                queue.task_done()

    async def runner():
        # Create queue and add all domains
        queue = asyncio.Queue()
        for domain in to_crawl:
            await queue.put(domain)

        # Start worker pool
        workers = [asyncio.create_task(worker(queue)) for _ in range(max_parallel_domains)]

        # Wait for all domains to be processed
        await queue.join()

        # Stop workers
        for _ in range(max_parallel_domains):
            await queue.put(None)  # Poison pill
        await asyncio.gather(*workers)

    # Run crawler
    await runner()

    pbar.close()

    # Calculate statistics
    total_pages = sum(r.get("pages_crawled", 0) for r in results)
    successful = sum(1 for r in results if r.get("success", False))

    return {
        "total_domains": len(domains),
        "crawled_domains": successful,
        "skipped_domains": len(domains) - len(to_crawl),
        "total_pages": total_pages,
        "results": results
    }
