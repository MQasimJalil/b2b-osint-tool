"""
Discovery Repository

CRUD operations for discovery-related documents (DiscoveredDomain, QueryCache, VettingResult).
"""

from typing import List, Optional, Dict, Any, Set
from datetime import datetime

from ..mongodb_models import DiscoveredDomain, QueryCache, VettingResult


# ============================================
# Discovered Domains
# ============================================

async def add_discovered_domain(
    domain: str,
    engine: str,
    query: str,
    user_id: Optional[str] = None,
    vetting_result: Optional[Dict[str, bool]] = None
) -> DiscoveredDomain:
    """Add a discovered domain"""
    data = {
        'domain': domain,
        'engine': engine,
        'query': query,
        'user_id': user_id,
        'discovered_at': datetime.utcnow()
    }

    if vetting_result:
        data.update({
            'has_cart': vetting_result.get('has_cart', False),
            'has_product_schema': vetting_result.get('has_product_schema', False),
            'has_platform_fp': vetting_result.get('has_platform_fp', False)
        })

    discovered = DiscoveredDomain(**data)
    await discovered.insert()
    return discovered


async def get_discovered_domains(
    skip: int = 0,
    limit: int = 100
) -> List[DiscoveredDomain]:
    """Get all discovered domains"""
    return await DiscoveredDomain.find().skip(skip).limit(limit).to_list()


async def get_discovered_domains_set() -> Set[str]:
    """Get set of all discovered domain names (for deduplication)"""
    domains = await DiscoveredDomain.find_all().to_list()
    return {d.domain for d in domains if d.domain}


# ============================================
# Query Cache
# ============================================

async def save_query_cache(
    engine: str,
    query: str,
    domains: List[str]
) -> QueryCache:
    """Save completed query to cache"""
    # Try to update existing, or create new
    existing = await QueryCache.find_one(
        QueryCache.engine == engine,
        QueryCache.query == query
    )

    if existing:
        existing.domains = domains
        existing.completed_at = datetime.utcnow()
        await existing.save()
        return existing
    else:
        cache = QueryCache(
            engine=engine,
            query=query,
            domains=domains,
            completed_at=datetime.utcnow()
        )
        await cache.insert()
        return cache


async def get_completed_queries() -> Set[str]:
    """Get set of completed query keys (engine::query format)"""
    queries = await QueryCache.find().to_list()
    return {f"{q.engine}::{q.query}" for q in queries}


async def is_query_completed(engine: str, query: str) -> bool:
    """Check if a query has been completed"""
    cache = await QueryCache.find_one(
        QueryCache.engine == engine,
        QueryCache.query == query
    )
    return cache is not None


# ============================================
# Vetting Results
# ============================================

async def save_vetting_result(
    domain: str,
    has_product_schema: bool = False,
    has_cart: bool = False,
    has_platform_fp: bool = False,
    decision: str = "UNKNOWN"
) -> VettingResult:
    """Save or update vetting result for a domain"""
    # Try to update existing
    existing = await VettingResult.find_one(VettingResult.domain == domain)

    if existing:
        existing.has_product_schema = has_product_schema
        existing.has_cart = has_cart
        existing.has_platform_fp = has_platform_fp
        existing.decision = decision
        existing.vetted_at = datetime.utcnow()
        await existing.save()
        return existing
    else:
        result = VettingResult(
            domain=domain,
            has_product_schema=has_product_schema,
            has_cart=has_cart,
            has_platform_fp=has_platform_fp,
            decision=decision,
            vetted_at=datetime.utcnow()
        )
        await result.insert()
        return result


async def get_vetting_result(domain: str) -> Optional[Dict[str, bool]]:
    """Get vetting result for a domain"""
    result = await VettingResult.find_one(VettingResult.domain == domain)
    if result:
        return {
            'has_product_schema': result.has_product_schema,
            'has_cart': result.has_cart,
            'has_platform_fp': result.has_platform_fp
        }
    return None


async def update_vetting_decision(domain: str, decision: str) -> bool:
    """Update vetting decision for a domain"""
    result = await VettingResult.find_one(VettingResult.domain == domain)
    if result:
        result.decision = decision
        result.vetted_at = datetime.utcnow()
        await result.save()
        return True
    return False


# ============================================
# Synchronous Wrappers (for sync code like discovery service)
# ============================================

import asyncio


def add_discovered_domain_sync(
    domain: str,
    engine: str,
    query: str,
    user_id: Optional[str] = None,
    vetting_result: Optional[Dict[str, bool]] = None
) -> DiscoveredDomain:
    """Sync wrapper for add_discovered_domain"""
    return asyncio.run(add_discovered_domain(domain, engine, query, user_id, vetting_result))


def get_discovered_domains_set_sync() -> Set[str]:
    """Sync wrapper for get_discovered_domains_set"""
    return asyncio.run(get_discovered_domains_set())


def save_query_cache_sync(engine: str, query: str, domains: List[str]) -> QueryCache:
    """Sync wrapper for save_query_cache"""
    return asyncio.run(save_query_cache(engine, query, domains))


def get_completed_queries_sync() -> Set[str]:
    """Sync wrapper for get_completed_queries"""
    return asyncio.run(get_completed_queries())


def save_vetting_result_sync(
    domain: str,
    has_product_schema: bool = False,
    has_cart: bool = False,
    has_platform_fp: bool = False,
    decision: str = "UNKNOWN"
) -> VettingResult:
    """Sync wrapper for save_vetting_result"""
    return asyncio.run(save_vetting_result(domain, has_product_schema, has_cart, has_platform_fp, decision))


def get_vetting_result_sync(domain: str) -> Optional[Dict[str, bool]]:
    """Sync wrapper for get_vetting_result"""
    return asyncio.run(get_vetting_result(domain))
