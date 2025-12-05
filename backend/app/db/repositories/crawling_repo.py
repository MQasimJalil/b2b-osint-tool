"""
Crawling Repository

Data access layer for crawl state and crawled pages.
"""

import asyncio
from typing import List, Dict, Optional, Set
from datetime import datetime
from beanie.operators import In
import concurrent.futures
from functools import wraps

from app.db.mongodb_models import CrawlState, CrawledPage
from app.db.mongodb_session import get_database


def _run_async_in_thread(coro):
    """
    Run an async coroutine in a separate thread with its own event loop.
    This allows calling async functions from within an existing event loop.
    """
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    # Check if we're already in an event loop
    try:
        asyncio.get_running_loop()
        # We're in an event loop, run in thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result()
    except RuntimeError:
        # No running event loop, safe to use asyncio.run
        return asyncio.run(coro)


# ============================================================================
# Crawl State Operations
# ============================================================================

async def get_crawl_state(domain: str) -> Optional[CrawlState]:
    """Get crawl state for a domain"""
    return await CrawlState.find_one({"domain": domain})


async def create_crawl_state(
    domain: str,
    visited_urls: List[str] = None,
    content_hashes: List[str] = None,
    is_complete: bool = False
) -> CrawlState:
    """Create a new crawl state record"""
    state = CrawlState(
        domain=domain,
        visited_urls=visited_urls or [],
        visited_hashes=content_hashes or [],
        is_complete=is_complete,
        started_at=datetime.utcnow()
    )
    await state.insert()
    return state


async def update_crawl_state(
    domain: str,
    visited_urls: List[str] = None,
    content_hashes: List[str] = None,
    is_complete: bool = None,
    pages_crawled: int = None
) -> Optional[CrawlState]:
    """Update crawl state for a domain"""
    state = await get_crawl_state(domain)

    if not state:
        # Create new state if doesn't exist
        return await create_crawl_state(
            domain=domain,
            visited_urls=visited_urls or [],
            content_hashes=content_hashes or [],
            is_complete=is_complete if is_complete is not None else False
        )

    # Update existing state
    if visited_urls is not None:
        state.visited_urls = visited_urls
    if content_hashes is not None:
        state.visited_hashes = content_hashes
    if is_complete is not None:
        state.is_complete = is_complete
    if pages_crawled is not None:
        state.pages_crawled = pages_crawled

    if is_complete:
        state.completed_at = datetime.utcnow()

    await state.save()
    return state


async def mark_crawl_complete(domain: str, pages_crawled: int, unique_pages: int) -> Optional[CrawlState]:
    """Mark a crawl as completed"""
    return await update_crawl_state(
        domain=domain,
        is_complete=True,
        pages_crawled=unique_pages
    )


async def get_visited_urls(domain: str) -> Set[str]:
    """Get set of visited URLs for a domain"""
    state = await get_crawl_state(domain)
    if state and state.visited_urls:
        return set(state.visited_urls)
    return set()


async def get_content_hashes(domain: str) -> Set[str]:
    """Get set of content hashes for a domain"""
    state = await get_crawl_state(domain)
    if state and state.visited_hashes:
        return set(state.visited_hashes)
    return set()


async def is_domain_crawled(domain: str) -> bool:
    """Check if domain has been fully crawled"""
    state = await get_crawl_state(domain)
    return state is not None and state.is_complete


async def get_crawl_status_batch(domains: List[str]) -> Dict[str, Dict]:
    """Get crawl status for multiple domains"""
    # Use dict syntax for 'in' query: {"domain": {"$in": domains}}
    states = await CrawlState.find({"domain": {"$in": domains}}).to_list()

    status_map = {}
    for state in states:
        status_map[state.domain] = {
            "fully_crawled": state.is_complete,
            "pages": state.pages_crawled or 0,
            "visited_urls": len(state.visited_urls) if state.visited_urls else 0,
            "in_progress": not state.is_complete and (state.pages_crawled or 0) > 0,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "completed_at": state.completed_at.isoformat() if state.completed_at else None
        }

    # Add domains not in DB (not started)
    for domain in domains:
        if domain not in status_map:
            status_map[domain] = {
                "fully_crawled": False,
                "pages": 0,
                "visited_urls": 0,
                "in_progress": False,
                "started_at": None,
                "completed_at": None
            }

    return status_map


# ============================================================================
# Crawled Pages Operations
# ============================================================================

async def save_crawled_page(
    domain: str,
    url: str,
    title: Optional[str],
    content: str,
    content_hash: str,
    depth: int,
    links: List[str] = None
) -> CrawledPage:
    """Save a crawled page"""
    page = CrawledPage(
        domain=domain,
        url=url,
        title=title,
        content=content,
        content_hash=content_hash,
        depth=depth,
        links=links or [],
        crawled_at=datetime.utcnow()
    )
    await page.insert()
    return page


async def get_crawled_pages(domain: str, limit: int = 1000) -> List[CrawledPage]:
    """Get crawled pages for a domain"""
    return await CrawledPage.find({"domain": domain}).limit(limit).to_list()


async def get_crawled_page_count(domain: str) -> int:
    """Get count of crawled pages for a domain"""
    return await CrawledPage.find({"domain": domain}).count()


async def get_homepage(domain: str) -> Optional[CrawledPage]:
    """Get homepage (depth=0) for a domain"""
    return await CrawledPage.find_one(
        {"domain": domain, "depth": 0}
    )


async def delete_crawled_pages(domain: str) -> int:
    """Delete all crawled pages for a domain"""
    result = await CrawledPage.find({"domain": domain}).delete()
    return result.deleted_count


async def delete_crawled_pages_by_domain(domain: str) -> int:
    """Delete all crawled pages for a domain (alias for delete_crawled_pages)"""
    return await delete_crawled_pages(domain)


# ============================================================================
# Sync Wrappers (for synchronous code)
# ============================================================================

def get_crawl_state_sync(domain: str) -> Optional[CrawlState]:
    """Sync wrapper for get_crawl_state"""
    return _run_async_in_thread(get_crawl_state(domain))


def update_crawl_state_sync(
    domain: str,
    visited_urls: List[str] = None,
    content_hashes: List[str] = None,
    is_complete: bool = None,
    pages_crawled: int = None
) -> Optional[CrawlState]:
    """Sync wrapper for update_crawl_state"""
    return _run_async_in_thread(update_crawl_state(domain, visited_urls, content_hashes, is_complete, pages_crawled))


def get_visited_urls_sync(domain: str) -> Set[str]:
    """Sync wrapper for get_visited_urls"""
    return _run_async_in_thread(get_visited_urls(domain))


def get_content_hashes_sync(domain: str) -> Set[str]:
    """Sync wrapper for get_content_hashes"""
    return _run_async_in_thread(get_content_hashes(domain))


def is_domain_crawled_sync(domain: str) -> bool:
    """Sync wrapper for is_domain_crawled"""
    return _run_async_in_thread(is_domain_crawled(domain))


def get_crawl_status_batch_sync(domains: List[str]) -> Dict[str, Dict]:
    """Sync wrapper for get_crawl_status_batch"""
    return _run_async_in_thread(get_crawl_status_batch(domains))


def mark_crawl_complete_sync(domain: str, pages_crawled: int, unique_pages: int) -> Optional[CrawlState]:
    """Sync wrapper for mark_crawl_complete"""
    return _run_async_in_thread(mark_crawl_complete(domain, pages_crawled, unique_pages))


def save_crawled_page_sync(
    domain: str,
    url: str,
    title: Optional[str],
    content: str,
    content_hash: str,
    depth: int,
    links: List[str] = None
) -> CrawledPage:
    """Sync wrapper for save_crawled_page"""
    return _run_async_in_thread(save_crawled_page(domain, url, title, content, content_hash, depth, links))


def get_crawled_pages_sync(domain: str, limit: int = 1000) -> List[CrawledPage]:
    """Sync wrapper for get_crawled_pages"""
    return _run_async_in_thread(get_crawled_pages(domain, limit))


def get_crawled_page_count_sync(domain: str) -> int:
    """Sync wrapper for get_crawled_page_count"""
    return _run_async_in_thread(get_crawled_page_count(domain))
