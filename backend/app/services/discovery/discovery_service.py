"""
Discovery service for finding companies through search engines.
"""
from typing import List, Dict, Optional, Callable, Set
import asyncio
import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from .search_engines import get_search_engine, SearchEngine
from .proxy_manager import ProxyManager, create_proxy_manager
from .query_generator import generate_queries, QueryGeneratorConfig
from ..vetting.enhanced_vet import vet_domains_batch, extract_domain_root
from ...db.session import SessionLocal
from ...db import models
from ...db.models import Company
from ...crud import companies as crud_companies
from ...db.repositories import company_repo

logger = logging.getLogger(__name__)


def extract_domain_name(domain: str) -> str:
    """
    Extract just the domain name without TLD for aggressive deduplication.

    This treats different TLDs as duplicates:
        theoneglove.com -> theoneglove
        theoneglove.com.au -> theoneglove
        theoneglove.us -> theoneglove
        www.theoneglove.com -> theoneglove

    Args:
        domain: Full domain (e.g., "theoneglove.com.au")

    Returns:
        Domain name without TLD (e.g., "theoneglove")
    """
    parts = domain.lower().split('.')

    # Remove www, shop, store, etc. prefixes
    common_subdomains = ['www', 'shop', 'store', 'web', 'online', 'buy', 'get']
    while len(parts) > 2 and parts[0] in common_subdomains:
        parts = parts[1:]

    # Handle multi-part TLDs like .co.uk, .com.au, .co.nz
    if len(parts) >= 3 and parts[-2] in ['co', 'com', 'net', 'org', 'ac', 'gov', 'edu']:
        # example.co.uk -> example
        return parts[-3]
    elif len(parts) >= 2:
        # example.com -> example
        return parts[-2]

    # Single part domain (shouldn't happen but handle it)
    return parts[0] if parts else domain


class DiscoveryConfig:
    """Configuration for discovery jobs."""

    def __init__(
        self,
        keywords: List[str],
        search_engines: List[str] = None,
        region: str = "US",
        max_results_per_keyword: int = 100,
        max_results_per_engine: int = 50,
        proxy_mode: str = "none",
        proxies: Optional[List[str]] = None,
        google_api_key: Optional[str] = None,
        google_search_engine_id: Optional[str] = None,
        bing_api_key: Optional[str] = None,
        deduplicate: bool = True,
        user_id: Optional[int] = None,
        # Query generation parameters
        max_queries: int = 400,
        negative_keywords: Optional[List[str]] = None,
        geo_regions: Optional[List[str]] = None,
        geo_tlds: Optional[List[str]] = None
    ):
        self.keywords = keywords
        self.search_engines = search_engines or ["google"]
        self.region = region
        self.max_results_per_keyword = max_results_per_keyword
        self.max_results_per_engine = max_results_per_engine
        self.proxy_mode = proxy_mode
        self.proxies = proxies
        self.google_api_key = google_api_key
        self.google_search_engine_id = google_search_engine_id
        self.bing_api_key = bing_api_key
        self.deduplicate = deduplicate
        self.user_id = user_id
        # Query generation
        self.max_queries = max_queries
        self.negative_keywords = negative_keywords or []
        self.geo_regions = geo_regions or []
        self.geo_tlds = geo_tlds or []


class DiscoveryService:
    """Service for discovering companies through search engines."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self._should_close_db = False

        if not self.db:
            self.db = SessionLocal()
            self._should_close_db = True

    def __del__(self):
        """Close database session if we created it."""
        if self._should_close_db and self.db:
            try:
                self.db.close()
            except:
                pass

    async def discover(
        self,
        config: DiscoveryConfig,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> Dict[str, any]:
        """
        Run discovery process based on configuration.

        Args:
            config: Discovery configuration
            progress_callback: Optional callback function to report progress (0-100)

        Returns:
            Dict containing discovered domains, statistics, and metadata
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting discovery with {len(config.keywords)} keywords and {len(config.search_engines)} engines")

        # Generate sophisticated search queries using AI variants + query families
        logger.info(f"Generating comprehensive search queries for {len(config.keywords)} base keywords...")

        # Create query generator configuration from discovery config
        query_config = QueryGeneratorConfig(
            use_ai_variants=True,
            max_queries=config.max_queries,
            per_family_cap=50,
            regions=config.geo_regions,
            geo_tlds=config.geo_tlds,
            negative_keywords=config.negative_keywords,
        )

        expanded_queries, keyword_variants = await generate_queries(config.keywords, query_config)
        logger.info(f"Generated {len(expanded_queries)} search queries from {len(config.keywords)} base keywords")
        logger.info(f"Generated {len(keyword_variants)} keyword variants (will be reused in vetting to avoid duplicate API calls)")

        # Initialize proxy manager
        proxy_manager = create_proxy_manager(
            mode=config.proxy_mode,
            proxies=config.proxies
        )
        await proxy_manager.start()

        try:
            # Track detailed query execution
            query_executions = []

            # Collect results from all search engines
            all_results = []
            total_tasks = len(expanded_queries) * len(config.search_engines)
            completed_tasks = 0

            for keyword in expanded_queries:
                for engine_name in config.search_engines:
                    query_start = datetime.utcnow()
                    query_success = False
                    query_error = None
                    query_results_count = 0
                    query_domains = []

                    try:
                        # Get search engine instance
                        engine = get_search_engine(
                            engine=engine_name,
                            google_api_key=config.google_api_key,
                            google_search_engine_id=config.google_search_engine_id,
                            bing_api_key=config.bing_api_key,
                            proxy_manager=proxy_manager
                        )

                        # Perform search
                        results = await engine.search(
                            query=keyword,
                            max_results=config.max_results_per_engine,
                            region=config.region
                        )

                        all_results.extend(results)
                        query_results_count = len(results)
                        query_domains = [r.get("domain") for r in results if r.get("domain")]
                        query_success = True
                        logger.info(f"Found {len(results)} results for '{keyword}' on {engine_name}")

                    except Exception as e:
                        query_error = str(e)
                        logger.error(f"Error searching {engine_name} for '{keyword}': {e}")

                    finally:
                        # Record query execution details
                        query_end = datetime.utcnow()
                        query_executions.append({
                            "query": keyword,
                            "engine": engine_name,
                            "results_count": query_results_count,
                            "domains": query_domains,
                            "success": query_success,
                            "error": query_error,
                            "started_at": query_start.isoformat(),
                            "completed_at": query_end.isoformat(),
                            "duration_seconds": (query_end - query_start).total_seconds()
                        })

                        # Update progress
                        completed_tasks += 1
                        if progress_callback:
                            progress = int((completed_tasks / total_tasks) * 90)  # Leave 10% for deduplication
                            progress_callback(progress)

            # Deduplicate results
            if config.deduplicate:
                unique_results = self._deduplicate_results(all_results)
                logger.info(f"Deduplicated {len(all_results)} results to {len(unique_results)} unique domains")
            else:
                unique_results = all_results

            # Save discovered domains to database (includes vetting)
            vetting_stats = await self._save_discovered_domains(
                unique_results,
                config.user_id,
                config.keywords,
                keyword_variants
            )

            # Final progress update
            if progress_callback:
                progress_callback(100)

            # Calculate total execution time
            end_time = datetime.utcnow()
            total_duration = (end_time - start_time).total_seconds()

            # Prepare result with detailed metadata
            result = {
                "total_results": len(all_results),
                "unique_domains": len(unique_results),
                "vetted": vetting_stats.get("vetted", 0),
                "approved_domains": vetting_stats.get("approved", 0),
                "rejected_domains": vetting_stats.get("rejected", 0),
                "saved_domains": vetting_stats.get("saved", 0),
                "base_keywords": config.keywords,  # Original user keywords
                "expanded_queries": expanded_queries,  # All generated queries
                "keywords": config.keywords,  # Keep for backward compatibility
                "search_engines": config.search_engines,
                "region": config.region,
                "domains": [r["domain"] for r in unique_results if r.get("domain")],
                "proxy_stats": proxy_manager.get_proxy_stats() if config.proxy_mode != "none" else None,
                # Enhanced metadata
                "query_executions": query_executions,
                "execution_summary": {
                    "started_at": start_time.isoformat(),
                    "completed_at": end_time.isoformat(),
                    "total_duration_seconds": total_duration,
                    "total_queries": len(query_executions),
                    "successful_queries": sum(1 for q in query_executions if q["success"]),
                    "failed_queries": sum(1 for q in query_executions if not q["success"]),
                    "base_keywords_count": len(config.keywords),
                    "expanded_queries_count": len(expanded_queries)
                },
                # Detailed vetting results for all domains
                "vetting_details": vetting_stats.get("vetting_details", [])
            }

            logger.info(
                f"Discovery complete: {result['unique_domains']} unique domains found, "
                f"{result['approved_domains']} approved, {result['rejected_domains']} rejected, "
                f"{result['saved_domains']} saved in {total_duration:.2f}s"
            )
            return result

        finally:
            await proxy_manager.stop()

    def _deduplicate_results(self, results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Deduplicate search results by domain NAME (ignoring TLDs and subdomains).

        Examples:
            www.example.com and shop.example.com -> only keep one
            example.com and example.co.uk -> only keep one (same brand name)
            theoneglove.com and theoneglove.com.au -> only keep one (same brand)

        Args:
            results: List of search results

        Returns:
            List of unique search results (first occurrence of each domain name)
        """
        seen_domain_names: Set[str] = set()
        unique_results = []

        for result in results:
            domain = result["domain"]
            if not domain:
                continue

            # Extract just the domain name (without TLD or subdomain)
            domain_name = extract_domain_name(domain)

            if domain_name not in seen_domain_names:
                seen_domain_names.add(domain_name)
                # Keep the original full domain in the result
                unique_results.append(result)
            else:
                logger.debug(f"Skipping duplicate domain name: {domain} (name: {domain_name})")

        logger.info(f"Deduplicated {len(results)} results to {len(unique_results)} unique base domains")
        return unique_results

    async def _save_discovered_domains(
        self,
        results: List[Dict[str, str]],
        user_id: Optional[int],
        keywords: List[str],
        keyword_variants: List[str]
    ) -> Dict[str, int]:
        """
        Vet and save discovered domains to database.

        This performs the following steps:
        1. Vet all domains (check e-commerce + keyword relevance)
        2. Save approved domains to database with vetting details
        3. Mark rejected domains in discovery log

        Args:
            results: List of discovery results
            user_id: User ID who initiated the discovery
            keywords: Keywords used for discovery
            keyword_variants: Pre-generated keyword variants (passed to vetting to avoid duplicate API calls)

        Returns:
            Dict with counts: {total, vetted, approved, rejected, saved}
        """
        if not user_id:
            logger.warning("No user_id provided, skipping domain save")
            return {"total": 0, "vetted": 0, "approved": 0, "rejected": 0, "saved": 0}

        total_count = len(results)
        domains_to_vet = [r["domain"] for r in results if r.get("domain")]

        logger.info(f"Vetting {len(domains_to_vet)} domains for relevance...")
        logger.info(f"Using {len(keyword_variants)} pre-generated keyword variants (avoiding duplicate API calls)")

        # Vet all domains concurrently, passing keyword variants to avoid regenerating them
        # Using more lenient thresholds: min_ecommerce_keywords=1 (down from 2), min_relevance_score=0.2 (down from 0.3)
        approved_vetting, rejected_vetting = await vet_domains_batch(
            domains=domains_to_vet,
            search_keywords=keywords,
            min_ecommerce_keywords=1,  # More lenient: accept domains with at least 1 e-commerce keyword
            min_relevance_score=0.2,   # More lenient: accept domains with at least 20% relevance
            keyword_variants=keyword_variants  # Pass pre-generated variants to avoid duplicate API calls
        )

        # Create mapping of domain -> vetting result
        vetting_map = {}
        all_vetting_results = []
        for vet_result in (approved_vetting + rejected_vetting):
            vetting_map[vet_result["domain"]] = vet_result
            all_vetting_results.append(vet_result)

        # Create or get existing discovery query record
        query_text = ", ".join(keywords)
        discovery_query = self.db.query(models.DiscoveryQuery).filter(
            models.DiscoveryQuery.engine == "multi",
            models.DiscoveryQuery.query == query_text
        ).first()

        if not discovery_query:
            discovery_query = models.DiscoveryQuery(
                engine="multi",
                query=query_text
            )
            self.db.add(discovery_query)
            self.db.flush()  # Get the query ID
        else:
            logger.info(f"Reusing existing discovery query ID: {discovery_query.id}")

        saved_count = 0

        # Save only approved domains
        for result in results:
            domain = result["domain"]
            if not domain:
                continue

            vet_result = vetting_map.get(domain)
            if not vet_result:
                logger.warning(f"No vetting result for {domain}, skipping")
                continue

            try:
                # Check if domain already exists
                existing_domain = self.db.query(models.DiscoveredDomain).filter(
                    models.DiscoveredDomain.domain == domain,
                    models.DiscoveredDomain.query_id == discovery_query.id
                ).first()

                if not existing_domain:
                    # Create discovered domain record
                    discovered_domain = models.DiscoveredDomain(
                        domain=domain,
                        query_id=discovery_query.id,
                        engine=result.get("source", "unknown")
                    )
                    self.db.add(discovered_domain)

                # Only create company record if vetting approved
                if vet_result["status"] == "approved":
                    # Check if company exists with exact domain match
                    existing_company = crud_companies.get_company_by_domain(self.db, domain)

                    if not existing_company:
                        # Also check for similar domains across existing companies (cross-discovery deduplication)
                        domain_name = extract_domain_name(domain)
                        all_existing_companies = self.db.query(models.Company).filter(
                            models.Company.user_id == user_id
                        ).all()

                        is_duplicate = False
                        for existing in all_existing_companies:
                            existing_domain_name = extract_domain_name(existing.domain)
                            if domain_name == existing_domain_name:
                                is_duplicate = True
                                logger.debug(
                                    f"Skipping duplicate domain: {domain} (duplicate of existing: {existing.domain})"
                                )
                                # Create domain alias record for tracking
                                try:
                                    alias = models.DomainAlias(
                                        primary_domain=existing.domain,
                                        alias_domain=domain,
                                        confidence=0.9,
                                        source="discovery_deduplication"
                                    )
                                    self.db.add(alias)
                                except Exception as alias_error:
                                    logger.debug(f"Could not create alias record: {alias_error}")
                                break

                        if not is_duplicate:
                            # Create company profile with vetting details
                            company = models.Company(
                                user_id=user_id,
                                domain=domain,
                                company_name=result.get("title", ""),
                                description=result.get("snippet", ""),
                                search_mode="discovery",
                                vetting_status="approved",
                                vetting_score=vet_result.get("relevance_score", 0.0),
                                vetting_details=json.dumps(vet_result),
                                vetted_at=datetime.utcnow(),
                                crawl_status="not_crawled"
                            )
                            self.db.add(company)
                            
                            # Sync to MongoDB for Frontend display
                            try:
                                # Resolve Auth0 ID from SQL User ID
                                auth0_id = str(user_id)
                                if user_id:
                                    user_obj = self.db.query(models.User).filter(models.User.id == user_id).first()
                                    if user_obj and user_obj.auth0_id:
                                        auth0_id = user_obj.auth0_id

                                await company_repo.create_company({
                                    "user_id": auth0_id,
                                    "domain": domain,
                                    "company_name": result.get("title", "") or domain,
                                    "description": result.get("snippet", "") or "",
                                    "created_at": datetime.utcnow(),
                                    "updated_at": datetime.utcnow()
                                })
                            except Exception as mongo_e:
                                logger.error(f"Failed to sync discovered company {domain} to MongoDB: {mongo_e}")

                            saved_count += 1
                            logger.debug(f"Approved and saved: {domain} (score: {vet_result.get('relevance_score')})")
                else:
                    logger.debug(f"Rejected: {domain} - {vet_result.get('reason')}")

            except Exception as e:
                logger.error(f"Error saving domain {domain}: {e}")

        # Commit all changes
        try:
            self.db.commit()
            logger.info(f"Saved {saved_count} approved domains (rejected {len(rejected_vetting)})")
        except Exception as e:
            logger.error(f"Error committing discovered domains: {e}")
            self.db.rollback()
            saved_count = 0

        return {
            "total": total_count,
            "vetted": len(vetting_map),
            "approved": len(approved_vetting),
            "rejected": len(rejected_vetting),
            "saved": saved_count,
            "vetting_details": all_vetting_results  # Include detailed vetting results for all domains
        }

    async def get_discovery_history(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get discovery history for a user.

        Args:
            user_id: User ID
            limit: Maximum number of records to return

        Returns:
            List of discovery queries with domain counts
        """
        queries = self.db.query(models.DiscoveryQuery)\
            .order_by(models.DiscoveryQuery.executed_at.desc())\
            .limit(limit)\
            .all()

        history = []
        for query in queries:
            domain_count = self.db.query(models.DiscoveredDomain).filter(
                models.DiscoveredDomain.query_id == query.id
            ).count()

            history.append({
                "id": query.id,
                "engine": query.engine,
                "query": query.query,
                "executed_at": query.executed_at.isoformat() if query.executed_at else None,
                "domain_count": domain_count
            })

        return history
