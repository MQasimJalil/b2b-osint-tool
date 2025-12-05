"""
Celery tasks for background processing.
These tasks handle long-running operations like discovery, crawling, extraction, and enrichment.
"""
from typing import List, Dict, Any, Union
from celery import Task
from sqlalchemy.orm import Session

from celery_app import celery_app
from app.db.session import SessionLocal
from app.crud import companies as company_crud, users as user_crud


class DatabaseTask(Task):
    """Base task that provides database session."""
    _db: Session = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(name="backend.celery_app.tasks.discover_companies_task", base=DatabaseTask, bind=True)
def discover_companies_task(
    self: Task,
    job_id: str,
    config: Dict[str, Any],
    user_id: int
) -> Dict[str, Any]:
    """
    Task to discover companies based on search configuration.

    Args:
        job_id: Job ID for tracking
        config: Discovery configuration dictionary
        user_id: User ID who initiated the discovery

    Returns:
        Dictionary with discovered companies and statistics
    """
    import asyncio
    from app.services.discovery.discovery_service import DiscoveryService, DiscoveryConfig
    from app.crud import jobs as crud_jobs
    from app.schemas.job import JobStatus
    from app.core.event_bus import event_bus

    db = self.db

    try:
        # Import settings to get API keys
        from app.core.config import settings

        # Update job status to running
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.RUNNING
        )

        # Publish job started event (if event_bus is available)
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_started",
                {"job_id": job_id, "job_type": "discovery"},
                user_id=str(user_id)
            ))

        # Get API keys from settings (try both env variable names)
        google_api_key = (
            config.get("google_api_key") or
            settings.GOOGLE_SEARCH_KEY or
            settings.GOOGLE_API_KEY
        )
        google_search_engine_id = (
            config.get("google_search_engine_id") or
            settings.GOOGLE_SEARCH_ENGINE_ID or
            settings.GOOGLE_CSE_ID
        )
        bing_api_key = config.get("bing_api_key") or settings.BING_API_KEY

        # Create discovery config
        discovery_config = DiscoveryConfig(
            keywords=config.get("keywords", []),
            search_engines=config.get("search_engines", ["google"]),
            region=config.get("region", "US"),
            max_results_per_engine=config.get("max_results_per_engine", 50),
            proxy_mode=config.get("proxy_mode", "none"),
            proxies=config.get("proxies"),
            google_api_key=google_api_key,
            google_search_engine_id=google_search_engine_id,
            bing_api_key=bing_api_key,
            user_id=user_id
        )

        # Progress callback to update job progress
        def update_progress(progress: int):
            crud_jobs.update_job_status(
                db,
                job_id=job_id,
                status=JobStatus.RUNNING,
                progress=progress
            )
            # Publish progress event (if event_bus is available)
            if event_bus:
                asyncio.run(event_bus.publish(
                    "job_progress",
                    {"job_id": job_id, "progress": progress},
                    user_id=str(user_id)
                ))

        # Run discovery
        discovery_service = DiscoveryService(db=db)
        result = asyncio.run(discovery_service.discover(
            config=discovery_config,
            progress_callback=update_progress
        ))

        # Update job with results
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            result=result
        )

        # Publish job completed event (if event_bus is available)
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_completed",
                {
                    "job_id": job_id,
                    "job_type": "discovery",
                    "domain_count": result["unique_domains"]
                },
                user_id=str(user_id)
            ))

        return result

    except Exception as e:
        # Update job as failed
        error_msg = str(e)
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.FAILED,
            error=error_msg
        )

        # Publish job failed event (if event_bus is available)
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_failed",
                {"job_id": job_id, "job_type": "discovery", "error": error_msg},
                user_id=str(user_id)
            ))

        raise


@celery_app.task(name="backend.celery_app.tasks.crawl_company_website_task", base=DatabaseTask, bind=True)
def crawl_company_website_task(self: Task, company_id: Union[str, int]) -> Dict[str, Any]:
    """
    Task to crawl a company's website (MongoDB only, no filesystem).

    For the specified company:
    1. Update crawl_status to 'crawling'
    2. Run crawl service (stores in MongoDB only)
    3. Update crawl_status to 'completed' and crawled_pages
    4. Trigger extraction task

    Args:
        company_id: ID of the company to crawl (String or Int)

    Returns:
        Dictionary with crawl statistics
    """
    from datetime import datetime
    from app.services.crawling.crawl import crawl_domains_mongodb_only
    from app.db.repositories import company_repo, crawling_repo
    from app.db.mongodb_session import init_db
    import asyncio

    db = self.db

    async def run_async_task():
        print(f"DEBUG: run_async_task start. ID={company_id} Type={type(company_id)}")
        await init_db()
        
        # 1. Find Company
        mongo_company = None
        company_domain = None
        
        # Try MongoDB first
        if isinstance(company_id, str):
            print(f"DEBUG: Attempting Mongo lookup for {company_id}")
            try:
                mongo_company = await company_repo.get_company_by_id(company_id)
                print(f"DEBUG: Mongo lookup result: {mongo_company}")
            except Exception as e:
                print(f"DEBUG: Mongo lookup failed with error: {e}")
        
        if mongo_company:
            company_domain = mongo_company.domain
            
            # Update status in Mongo
            await crawling_repo.update_crawl_state(company_domain, is_complete=False)
            
            # Update Company model in Mongo
            mongo_company.crawl_status = 'crawling'
            mongo_company.crawl_progress = 0
            await mongo_company.save()
            
        else:
            # Try SQL Fallback
            if isinstance(company_id, int) or (isinstance(company_id, str) and company_id.isdigit()):
                sql_company = company_crud.get_company(db, int(company_id))
                if sql_company:
                    company_domain = sql_company.domain
                    # Update status in SQL
                    sql_company.crawl_status = 'crawling'
                    sql_company.crawl_progress = 0
                    db.commit()
        
        if not company_domain:
            raise ValueError(f"Company {company_id} not found in MongoDB or SQL")

        # 2. Crawl domain (MongoDB only)
        result = await crawl_domains_mongodb_only(
            domains=[company_domain],
            max_pages=2000,
            max_depth=3,
            skip_crawled=False,
            concurrency=5,
            max_parallel_domains=1
        )

        # 3. Handle Result
        domain_result = next(
            (r for r in result.get("results", []) if r.get("domain") == company_domain),
            None
        )

        if domain_result and domain_result.get("success"):
            pages_crawled = domain_result.get("pages_crawled", 0)
            
            # Update status to completed
            if mongo_company:
                # Fetch fresh in case of race conditions, though unlikely in this flow
                c = await company_repo.get_company_by_domain(company_domain)
                if c:
                    c.crawl_status = 'completed'
                    c.crawl_progress = 100
                    c.crawled_pages = pages_crawled
                    c.crawled_at = datetime.utcnow()
                    await c.save()
            else:
                # Update SQL
                sql_company = company_crud.get_company(db, int(company_id))
                if sql_company:
                    sql_company.crawl_status = 'completed'
                    sql_company.crawl_progress = 100
                    sql_company.crawled_pages = pages_crawled
                    sql_company.crawled_at = datetime.utcnow()
                    db.commit()

            # Trigger extraction task
            extract_company_data_task.delay(company_id)

            return {
                "company_id": company_id,
                "domain": company_domain,
                "pages_crawled": pages_crawled,
                "urls_visited": domain_result.get("urls_visited", 0),
                "status": "completed"
            }
        else:
            # Crawl failed
            if mongo_company:
                c = await company_repo.get_company_by_domain(company_domain)
                if c:
                    c.crawl_status = 'failed'
                    c.crawl_progress = 0
                    await c.save()
            else:
                sql_company = company_crud.get_company(db, int(company_id))
                if sql_company:
                    sql_company.crawl_status = 'failed'
                    sql_company.crawl_progress = 0
                    db.commit()

            error = domain_result.get("error", "Unknown error") if domain_result else "No result returned"
            return {
                "company_id": company_id,
                "domain": company_domain,
                "pages_crawled": 0,
                "status": "failed",
                "error": error
            }

    # Run the async task in a single event loop
    return asyncio.run(run_async_task())


@celery_app.task(name="backend.celery_app.tasks.crawl_companies_batch_task", soft_time_limit=23*60*60, base=DatabaseTask, bind=True)
def crawl_companies_batch_task(self: Task, company_ids: List[Union[str, int]], user_id: int) -> Dict[str, Any]:
    """
    Task to crawl multiple companies in batch (MongoDB only, no filesystem).

    For each company:
    1. Update crawl_status to 'queued' then 'crawling'
    2. Run crawl service (stores in MongoDB only)
    3. Update crawl_status to 'completed'
    4. Trigger extraction task

    Args:
        company_ids: List of company IDs to crawl (String or Int)
        user_id: User ID who initiated the crawl

    Returns:
        Dictionary with batch crawl statistics
    """
    from datetime import datetime
    from app.services.crawling.crawl import crawl_domains_mongodb_only
    from app.db.repositories import company_repo, crawling_repo
    from app.db.mongodb_session import init_db
    import asyncio

    db = self.db

    try:
        # Helper to resolve companies
        async def resolve_companies():
            await init_db()
            resolved_companies = []
            domains = []
            
            for company_id in company_ids:
                company = None
                source = None
                
                # Try Mongo
                if isinstance(company_id, str):
                    company = await company_repo.get_company_by_id(company_id)
                    if company:
                        source = "mongo"
                
                # Fallback SQL
                if not company and (isinstance(company_id, int) or (isinstance(company_id, str) and company_id.isdigit())):
                    company = company_crud.get_company(db, int(company_id))
                    if company:
                        source = "sql"
                
                if company:
                    resolved_companies.append({"obj": company, "source": source, "id": company_id})
                    domains.append(company.domain)
                    
                    # Update status
                    if source == "mongo":
                        company.crawl_status = 'queued'
                        await company.save()
                    else:
                        company.crawl_status = 'queued'
                        # SQL commit later
            
            db.commit()
            return resolved_companies, domains

        companies_data, domains = asyncio.run(resolve_companies())

        if not domains:
            return {
                "user_id": user_id,
                "total_companies": len(company_ids),
                "crawled_companies": 0,
                "total_pages": 0,
                "status": "no_companies",
                "message": "No valid companies found"
            }

        # Crawl all domains (MongoDB only)
        result = asyncio.run(crawl_domains_mongodb_only(
            domains=domains,
            max_pages=2000,
            max_depth=3,
            skip_crawled=False,
            concurrency=5,
            max_parallel_domains=3
        ))

        # Update each company based on result
        successful_crawls = 0
        
        async def update_results():
            for item in companies_data:
                company = item["obj"]
                source = item["source"]
                company_id = item["id"]
                
                domain_result = next(
                    (r for r in result.get("results", []) if r.get("domain") == company.domain),
                    None
                )

                if domain_result and domain_result.get("success"):
                    pages = domain_result.get("pages_crawled", 0)
                    # Update success
                    if source == "mongo":
                        company.crawl_status = 'completed'
                        company.crawl_progress = 100
                        company.crawled_pages = pages
                        company.crawled_at = datetime.utcnow()
                        await company.save()
                    else:
                        company.crawl_status = 'completed'
                        company.crawl_progress = 100
                        company.crawled_pages = pages
                        company.crawled_at = datetime.utcnow()
                        # SQL commit later

                    # Trigger extraction task
                    extract_company_data_task.delay(company_id)
                else:
                    # Update failure
                    if source == "mongo":
                        company.crawl_status = 'failed'
                        company.crawl_progress = 0
                        await company.save()
                    else:
                        company.crawl_status = 'failed'
                        company.crawl_progress = 0
        
        asyncio.run(update_results())
        db.commit()
        
        # Count successes
        successful_crawls = sum(1 for r in result.get("results", []) if r.get("success"))

        return {
            "user_id": user_id,
            "total_companies": len(company_ids),
            "crawled_companies": successful_crawls,
            "failed_companies": len(companies_data) - successful_crawls,
            "total_pages": result.get("total_pages", 0),
            "status": "completed"
        }

    except Exception as e:
        # Update all companies to failed
        # Note: Detailed rollback logic skipped for brevity
        raise


@celery_app.task(name="backend.celery_app.tasks.extract_company_data_task", base=DatabaseTask, bind=True)
def extract_company_data_task(self: Task, company_id: Union[str, int]) -> Dict[str, Any]:
    """
    Task to extract data from crawled pages stored in MongoDB.

    1. Get crawled pages from MongoDB
    2. Extract company profile and products
    3. Save extracted data to database
    4. Trigger embedding task

    Args:
        company_id: ID of the company (String or Int)

    Returns:
        Dictionary with extracted data
    """
    import asyncio
    from datetime import datetime
    from app.db.repositories.crawling_repo import get_crawled_pages
    from app.db.repositories import company_repo
    from app.db.mongodb_session import init_db

    db = self.db

    try:
        # Helper to run async DB operations
        async def setup_and_get_data():
            await init_db()
            
            # Find Company
            company = None
            if isinstance(company_id, str):
                company = await company_repo.get_company_by_id(company_id)
            
            if not company and (isinstance(company_id, int) or (isinstance(company_id, str) and company_id.isdigit())):
                company = company_crud.get_company(db, int(company_id))
            
            if not company:
                return None, []

            # Get pages
            pages = await get_crawled_pages(company.domain, limit=1000)
            return company, pages

        company, crawled_pages = asyncio.run(setup_and_get_data())

        if not company:
            raise ValueError(f"Company {company_id} not found")

        if not crawled_pages:
            return {
                "company_id": company_id,
                "domain": company.domain,
                "products_extracted": 0,
                "contacts_extracted": 0,
                "status": "no_data",
                "message": "No crawled pages found in MongoDB"
            }

        print(f"[{company.domain}] Found {len(crawled_pages)} crawled pages in MongoDB")

        # Convert MongoDB documents to dict format for extraction
        pages_data = []
        for page in crawled_pages:
            pages_data.append({
                "url": page.url,
                "title": page.title,
                "content": page.content,
                "depth": page.depth
            })

        # Import extraction functions
        from app.services.extraction.extract import _chunk_pages, _merge_profiles, _merge_products, _get_async_client
        from openai import AsyncOpenAI
        import json

        # Extract company profile using OpenAI (inline to avoid MongoDB access issues)
        print(f"[{company.domain}] Extracting company profile...")

        # Prioritize contact/about pages
        priority_pages = []
        other_pages = []
        for p in pages_data:
            url_lower = p.get("url", "").lower()
            if any(kw in url_lower for kw in ["/about", "/contact", "/team", "/company", "/who-we-are"]) or p.get("depth", 0) == 0:
                priority_pages.append(p)
            else:
                other_pages.append(p)

        ordered_pages = priority_pages + other_pages
        chunks = _chunk_pages(ordered_pages, chars_per_chunk=60000)

        company_profile = None
        products = []

        if chunks:
            # Extract company profile
            from app.services.extraction.extract import _extract_profile_from_chunk, _retry_with_backoff, MAX_CONCURRENT_API_CALLS, REQUEST_DELAY

            async def extract_profile_async():
                client = _get_async_client()
                try:
                    semaphore = asyncio.Semaphore(MAX_CONCURRENT_API_CALLS)

                    async def limited_extract(chunk, index):
                        await asyncio.sleep(index * REQUEST_DELAY)
                        async with semaphore:
                            return await _retry_with_backoff(
                                _extract_profile_from_chunk(client, company.domain, chunk),
                                max_retries=5,
                                domain=company.domain
                            )

                    tasks = [limited_extract(chunk, i) for i, chunk in enumerate(chunks)]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    valid_results = [r for r in results if not isinstance(r, Exception) and r]
                    return valid_results
                finally:
                    await client.close()

            # Run extraction in new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                profile_results = loop.run_until_complete(extract_profile_async())
                company_profile = _merge_profiles(profile_results, company.domain)
                company_profile["extracted_at"] = datetime.utcnow().isoformat() + "Z"
                company_profile["crawled_pages"] = len(pages_data)
                company_profile["chunks_processed"] = len(chunks)
            finally:
                loop.close()

            print(f"[{company.domain}] Extracted company profile")

            # Extract products
            print(f"[{company.domain}] Extracting products...")
            product_pages = [p for p in pages_data if any(kw in p.get("url", "").lower() for kw in ["/product", "/shop", "/collection", "/catalog", "/store", "/glove"])]
            product_ordered = product_pages + [p for p in pages_data if p not in product_pages]
            product_chunks = _chunk_pages(product_ordered, chars_per_chunk=50000)

            if product_chunks:
                from app.services.extraction.extract import _extract_products_from_chunk

                async def extract_products_async():
                    client = _get_async_client()
                    try:
                        semaphore = asyncio.Semaphore(MAX_CONCURRENT_API_CALLS)

                        async def limited_extract(chunk, index):
                            await asyncio.sleep(index * REQUEST_DELAY)
                            async with semaphore:
                                return await _retry_with_backoff(
                                    _extract_products_from_chunk(client, company.domain, chunk, "goalkeeper gloves"),
                                    max_retries=5,
                                    domain=company.domain
                                )

                        tasks = [limited_extract(chunk, i) for i, chunk in enumerate(product_chunks)]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        valid_results = [r for r in results if not isinstance(r, Exception) and r]
                        return valid_results
                    finally:
                        await client.close()

                # Run extraction in new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    product_results = loop.run_until_complete(extract_products_async())
                    products = _merge_products(product_results, company.domain)
                    print(f"[{company.domain}] Extracted {len(products)} products")
                finally:
                    loop.close()

        # Save extracted data to MongoDB
        if company_profile or products:
            print(f"[{company.domain}] Saving extracted data...")

            from app.db.repositories.company_repo import update_company_profile
            from app.db.repositories.product_repo import create_products_bulk, delete_products_by_domain
            import app.db.mongodb_session as mongodb_session

            try:
                # Clear any existing event loop and force new MongoDB client
                asyncio.set_event_loop(None)

                # Force close old client to avoid "Event loop is closed" errors
                if mongodb_session._mongo_client:
                    mongodb_session._mongo_client.close()
                    mongodb_session._mongo_client = None
                    mongodb_session._initialized_loops.clear()

                # Create async save function
                async def save_all_data():
                    await init_db()

                    from app.db.repositories.company_repo import get_company_by_domain, create_company

                    # Check if company exists in MongoDB, create if not
                    mongodb_company = await get_company_by_domain(company.domain)
                    if not mongodb_company:
                        # Create minimal company record in MongoDB
                        # We need user_id from PostgreSQL company
                        from app.db.models import User as PGUser
                        
                        if isinstance(company.user_id, int):
                            pg_user = db.query(PGUser).filter(PGUser.id == company.user_id).first()
                        else:
                            pg_user = db.query(PGUser).filter(PGUser.auth0_id == str(company.user_id)).first()

                        mongodb_company = await create_company({
                            'user_id': str(pg_user.auth0_id) if pg_user else 'unknown',
                            'domain': company.domain,
                            'company_name': company_profile.get('company') if company_profile else None,
                            'created_at': datetime.utcnow(),
                            'updated_at': datetime.utcnow()
                        })
                        print(f"[{company.domain}] Created company in MongoDB with ID: {mongodb_company.id}")

                    company_id_str = str(mongodb_company.id)

                    # Update company profile if we have one
                    if company_profile:
                        await update_company_profile(company.domain, company_profile)
                        print(f"[{company.domain}] Updated company profile")

                    # Save products with company_id
                    if products:
                        for p in products:
                            p['domain'] = company.domain
                            p['company_id'] = company_id_str
                        await delete_products_by_domain(company.domain)
                        await create_products_bulk(products)
                        print(f"[{company.domain}] Saved {len(products)} products")

                # Run save operation with fresh event loop and client
                asyncio.run(save_all_data())
                print(f"[{company.domain}] Successfully saved all data to MongoDB")
            except Exception as e:
                print(f"[{company.domain}] Error saving to MongoDB: {e}")
                import traceback
                traceback.print_exc()
                raise

        # Check product relevance and mark company accordingly
        relevance_status = "pending"
        relevance_reason = None

        if len(products) == 0:
            # No relevant products found
            relevance_status = "irrelevant"
            relevance_reason = "No relevant products found after extraction"
            print(f"[{company.domain}] No relevant products found, marking as irrelevant")

            # Delete crawled pages from MongoDB to save space
            from app.db.repositories.crawling_repo import delete_crawled_pages_by_domain
            try:
                async def delete_pages():
                    await init_db()
                    deleted_count = await delete_crawled_pages_by_domain(company.domain)
                    print(f"[{company.domain}] Deleted {deleted_count} crawled pages")
                    return deleted_count

                asyncio.run(delete_pages())
            except Exception as e:
                print(f"[{company.domain}] Error deleting crawled pages: {e}")
        else:
            # Products found, mark as relevant
            relevance_status = "relevant"
            print(f"[{company.domain}] Found {len(products)} relevant products, marking as relevant")

        # Update relevance status in MongoDB
        try:
            async def update_relevance():
                await init_db()
                from app.db.repositories.company_repo import update_company_relevance
                await update_company_relevance(company.domain, relevance_status, relevance_reason)
                print(f"[{company.domain}] Updated relevance status to: {relevance_status}")

            asyncio.run(update_relevance())
        except Exception as e:
            print(f"[{company.domain}] Error updating relevance status: {e}")

        # Update company extracted_at timestamp
        company.extracted_at = datetime.utcnow()
        db.commit()

        # Only trigger embedding task if company is relevant (has products)
        if relevance_status == "relevant":
            embed_company_rag_task.delay(company_id)

        return {
            "company_id": company_id,
            "domain": company.domain,
            "pages_found": len(crawled_pages),
            "products_extracted": len(products) if products else 0,
            "contacts_extracted": len(company_profile.get("main_contacts", {}).get("email", [])) if company_profile else 0,
            "status": "completed",
            "message": f"Extracted company profile and {len(products) if products else 0} products from {len(crawled_pages)} pages."
        }

    except Exception as e:
        print(f"Error extracting data for company {company_id}: {e}")
        raise


@celery_app.task(name="backend.celery_app.tasks.enrich_company_contacts_task", base=DatabaseTask)
def enrich_company_contacts_task(company_id: int, sources: List[str]) -> Dict[str, Any]:
    """
    Task to enrich company contact information.

    Args:
        company_id: ID of the company
        sources: List of sources to use for enrichment

    Returns:
        Dictionary with enrichment results
    """
    # TODO: Implement enrichment logic using services
    # from ..app.services.enrichment import contact_enricher
    # company = company_crud.get_company(enrich_company_contacts_task.db, company_id)
    # results = contact_enricher.enrich_contacts(company.domain, sources)

    return {
        "company_id": company_id,
        "contacts_enriched": 0,
        "sources_used": sources,
        "status": "completed"
    }


@celery_app.task(name="backend.celery_app.tasks.generate_email_draft_task", base=DatabaseTask, bind=True)
def generate_email_draft_task(self: Task, company_id: Union[str, int], draft_id: Union[str, None] = None) -> Dict[str, Any]:
    """
    Task to generate an email draft for a company using AI.

    Args:
        company_id: ID of the company
        draft_id: Optional ID of the draft to update (preferred)

    Returns:
        Dictionary with draft information
    """
    import asyncio
    from app.db.mongodb_session import init_db
    from app.db.repositories import company_repo, campaign_repo
    from app.services.email.gemini_agent import GeminiAgent
    from app.crud import companies as company_crud

    db = self.db

    async def run_async_gen():
        await init_db()
        
        # 1. Resolve Company
        company = None
        if isinstance(company_id, str):
            company = await company_repo.get_company_by_id(company_id)
        
        # Fallback SQL -> Mongo
        if not company and (isinstance(company_id, int) or (isinstance(company_id, str) and company_id.isdigit())):
            sql_company = company_crud.get_company(db, int(company_id))
            if sql_company:
                company = await company_repo.get_company_by_domain(sql_company.domain)

        if not company:
            raise ValueError(f"Company {company_id} not found")

        # 2. Find the draft
        draft = None
        if draft_id:
            draft = await campaign_repo.get_draft(draft_id)
        
        # Fallback to latest if no ID provided
        if not draft:
            draft = await campaign_repo.get_draft_by_company(str(company.id))
            
        if not draft:
            raise ValueError(f"No draft found for company {company.id} (Draft ID: {draft_id})")

        try:
            # 3. Run Gemini Agent
            # Note: agent.run is synchronous/blocking, which is fine inside a Celery task
            # but we are inside an async wrapper. It will block the event loop, 
            # but since we only have one task here, it's acceptable.
            # Ideally run in executor if concurrent, but Celery is process-based.
            agent = GeminiAgent()
            result = agent.run(company.domain)

            if result.get("error"):
                raise Exception(result["error"])

            # 4. Update Draft
            update_data = {
                "subject": result["subject_lines"][0] if result["subject_lines"] else "No subject generated",
                "subject_line_options": result["subject_lines"],
                "body": result["email_body"],
                "status": "ready",
                "last_error": None
            }
            await campaign_repo.update_draft(str(draft.id), update_data)
            
            return {
                "company_id": str(company.id),
                "draft_id": str(draft.id),
                "status": "completed",
                "domain": company.domain
            }

        except Exception as e:
            # Update draft with error
            if draft:
                await campaign_repo.update_draft(str(draft.id), {
                    "status": "failed",
                    "last_error": str(e),
                    "body": f"Generation failed: {str(e)}"
                })
            raise

    return asyncio.run(run_async_gen())


@celery_app.task(name="backend.celery_app.tasks.send_email_task")
def send_email_task(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    """
    Task to send an email via Gmail API.

    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body

    Returns:
        Dictionary with send status
    """
    # TODO: Implement email sending logic using services
    # from ..app.services.email import gmail_sender
    # result = gmail_sender.send_email(to_email, subject, body)

    return {
        "to": to_email,
        "status": "sent"
    }


@celery_app.task(name="backend.celery_app.tasks.embed_company_rag_task", base=DatabaseTask, bind=True)
def embed_company_rag_task(self: Task, company_id: Union[str, int]) -> Dict[str, Any]:
    """
    Task to embed company data into MongoDB RAG vector database.

    Args:
        company_id: MongoDB ObjectId (str) or SQL ID (int) of the company

    Returns:
        Dictionary with embedding status
    """
    import asyncio
    from datetime import datetime
    from app.db.mongodb_session import init_db
    from app.db.repositories import company_repo
    from app.crud import companies as company_crud

    db = self.db

    try:
        # Helper to resolve Mongo Company ID
        async def resolve_company_id():
            await init_db()
            
            # If it looks like a Mongo ID, verify it
            if isinstance(company_id, str) and len(company_id) == 24:
                c = await company_repo.get_company_by_id(company_id)
                if c: return str(c.id)
            
            # If int or not found, check SQL to get domain
            domain = None
            if isinstance(company_id, int) or (isinstance(company_id, str) and company_id.isdigit()):
                sql_c = company_crud.get_company(db, int(company_id))
                if sql_c:
                    domain = sql_c.domain
            
            # If we have domain, find Mongo ID
            if domain:
                mongo_c = await company_repo.get_company_by_domain(domain)
                if mongo_c:
                    return str(mongo_c.id)
            
            # Fallback: maybe passed domain string?
            if isinstance(company_id, str):
                mongo_c = await company_repo.get_company_by_domain(company_id)
                if mongo_c:
                    return str(mongo_c.id)
                    
            return None

        target_id = asyncio.run(resolve_company_id())
        
        if not target_id:
             raise ValueError(f"Could not resolve MongoDB Company for ID: {company_id}")
             
        # Update variable to use resolved Mongo ID
        mongo_id_str = target_id

        # Get company from MongoDB
        from pymongo import MongoClient
        from bson import ObjectId
        import os

        mongo_uri = os.getenv("DATABASE_URL") or os.getenv("MONGODB_URI", "mongodb://mongodb:27017/b2b_osint")

        # Parse database name from URI
        if "/" in mongo_uri and mongo_uri.split("/")[-1]:
            db_name = mongo_uri.split("/")[-1]
            mongo_client_init = MongoClient(mongo_uri.rsplit("/", 1)[0])
        else:
            mongo_client_init = MongoClient(mongo_uri)
            db_name = os.getenv("MONGODB_DB", "b2b_osint")

        mongo_db_init = mongo_client_init[db_name]

        # Get company document
        company_doc_for_check = mongo_db_init.companies.find_one({"_id": ObjectId(mongo_id_str)})
        if not company_doc_for_check:
            mongo_client_init.close()
            raise ValueError(f"Company {mongo_id_str} not found")

        company_domain = company_doc_for_check["domain"]
        mongo_client_init.close()

        # Embed domain data into MongoDB RAG (fully synchronous approach)
        print(f"[{company_domain}] Embedding company data into RAG...")

        try:
            from app.services.rag.rag import semantic_chunk_text, _get_tokenizer, _sha256_text, _count_tokens
            from openai import OpenAI
            import os
            from pymongo import MongoClient

            # Get MongoDB connection
            # Use DATABASE_URL which is set in docker-compose.yml
            mongo_uri = os.getenv("DATABASE_URL") or os.getenv("MONGODB_URI", "mongodb://mongodb:27017/b2b_osint")

            # Parse database name from URI if it's in the URI, otherwise use env var
            if "/" in mongo_uri and mongo_uri.split("/")[-1]:
                db_name = mongo_uri.split("/")[-1]
                mongo_client = MongoClient(mongo_uri.rsplit("/", 1)[0])
            else:
                mongo_client = MongoClient(mongo_uri)
                db_name = os.getenv("MONGODB_DB", "b2b_osint")

            mongo_db = mongo_client[db_name]

            # Get crawled pages
            pages_cursor = mongo_db.crawled_pages.find({"domain": company_domain}).limit(1000)
            pages = list(pages_cursor)

            # Get products
            products_cursor = mongo_db.products.find({"domain": company_domain}).limit(500)
            products = list(products_cursor)

            # Get company profile
            company_doc = mongo_db.companies.find_one({"domain": company_domain})

            print(f"[{company_domain}] Found {len(pages)} pages, {len(products)} products")

            # Prepare chunks
            tokenizer = _get_tokenizer()
            raw_chunks = []

            # 1. Process crawled pages
            for page_idx, page in enumerate(pages):
                try:
                    url = page.get("url", "")
                    title = page.get("title", "")
                    content = page.get("content", "")
                    depth = page.get("depth", 0)

                    if not content:
                        continue

                    # Chunk the content semantically
                    page_chunks = semantic_chunk_text(content, tokenizer)

                    # Create chunk records
                    for chunk_idx, chunk_text in enumerate(page_chunks):
                        chunk_id = f"{company_domain}_page_{page_idx}_chunk_{chunk_idx}"
                        content_hash = _sha256_text(chunk_text)

                        chunk_record = {
                            "chunk_id": chunk_id,
                            "domain": company_domain,
                            "collection_name": "raw_pages",
                            "url": url,
                            "title": title,
                            "content": chunk_text,
                            "content_hash": content_hash,
                            "tokens": _count_tokens(chunk_text, tokenizer),
                            "metadata": {
                                "depth": depth,
                                "chunk_index": chunk_idx,
                                "total_chunks": len(page_chunks)
                            }
                        }
                        raw_chunks.append(chunk_record)
                except Exception as e:
                    print(f"[{company_domain}] Error processing page {page_idx}: {e}")
                    continue

            # 2. Process products
            for prod_idx, product in enumerate(products):
                try:
                    # Create product text representation
                    product_text_parts = []

                    if product.get("name"):
                        product_text_parts.append(f"Product: {product['name']}")

                    if product.get("brand"):
                        product_text_parts.append(f"Brand: {product['brand']}")

                    if product.get("category"):
                        product_text_parts.append(f"Category: {product['category']}")

                    if product.get("description"):
                        product_text_parts.append(f"Description: {product['description']}")

                    if product.get("price"):
                        product_text_parts.append(f"Price: {product['price']}")

                    if product.get("features"):
                        features = product['features']
                        if isinstance(features, list):
                            product_text_parts.append(f"Features: {', '.join(features)}")
                        elif isinstance(features, dict):
                            feature_list = [f"{k}: {v}" for k, v in features.items()]
                            product_text_parts.append(f"Features: {', '.join(feature_list)}")

                    product_text = "\n".join(product_text_parts)

                    if not product_text:
                        continue

                    # Chunk product text
                    product_chunks = semantic_chunk_text(product_text, tokenizer)

                    for chunk_idx, chunk_text in enumerate(product_chunks):
                        chunk_id = f"{company_domain}_product_{prod_idx}_chunk_{chunk_idx}"
                        content_hash = _sha256_text(chunk_text)

                        chunk_record = {
                            "chunk_id": chunk_id,
                            "domain": company_domain,
                            "collection_name": "products",
                            "url": product.get("url"),
                            "title": product.get("name"),
                            "content": chunk_text,
                            "content_hash": content_hash,
                            "tokens": _count_tokens(chunk_text, tokenizer),
                            "metadata": {
                                "product_id": str(product.get("_id")),
                                "category": product.get("category"),
                                "brand": product.get("brand"),
                                "chunk_index": chunk_idx,
                                "total_chunks": len(product_chunks)
                            }
                        }
                        raw_chunks.append(chunk_record)
                except Exception as e:
                    print(f"[{company_domain}] Error processing product {prod_idx}: {e}")
                    continue

            # 3. Process company profile
            if company_doc:
                try:
                    company_text_parts = []

                    if company_doc.get("company_name"):
                        company_text_parts.append(f"Company: {company_doc['company_name']}")

                    if company_doc.get("description"):
                        company_text_parts.append(f"Description: {company_doc['description']}")

                    if company_doc.get("smykm_notes"):
                        notes = company_doc['smykm_notes']
                        if isinstance(notes, list) and notes:
                            company_text_parts.append(f"Key Information:\n" + "\n".join(f"- {note}" for note in notes))

                    company_text = "\n".join(company_text_parts)

                    if company_text:
                        company_chunks = semantic_chunk_text(company_text, tokenizer)

                        for chunk_idx, chunk_text in enumerate(company_chunks):
                            chunk_id = f"{company_domain}_company_chunk_{chunk_idx}"
                            content_hash = _sha256_text(chunk_text)

                            chunk_record = {
                                "chunk_id": chunk_id,
                                "domain": company_domain,
                                "collection_name": "companies",
                                "url": f"https://{company_domain}",
                                "title": company_doc.get("company_name"),
                                "content": chunk_text,
                                "content_hash": content_hash,
                                "tokens": _count_tokens(chunk_text, tokenizer),
                                "metadata": {
                                    "company_id": str(company_doc.get("_id")),
                                    "chunk_index": chunk_idx,
                                    "total_chunks": len(company_chunks)
                                }
                            }
                            raw_chunks.append(chunk_record)
                except Exception as e:
                    print(f"[{company_domain}] Error processing company profile: {e}")

            print(f"[{company_domain}] Prepared {len(raw_chunks)} chunks from pages, products, and company data")

            if not raw_chunks:
                mongo_client.close()
                return {
                    "company_id": company_id,
                    "domain": company_domain,
                    "chunks_embedded": 0,
                    "status": "no_data",
                    "message": "No chunks to embed"
                }

            # Get existing chunk IDs from MongoDB to skip duplicates
            existing_chunk_ids = set()
            existing_embeddings = mongo_db.rag_embeddings.find(
                {"domain": company_domain},
                {"chunk_id": 1}
            )
            for emb in existing_embeddings:
                existing_chunk_ids.add(emb["chunk_id"])

            # Prepare batches for embedding
            chunks_to_embed = []
            for chunk in raw_chunks:
                if chunk["chunk_id"] not in existing_chunk_ids:
                    chunks_to_embed.append(chunk)

            print(f"[{company_domain}] {len(chunks_to_embed)} new chunks to embed, {len(raw_chunks) - len(chunks_to_embed)} skipped")

            if not chunks_to_embed:
                mongo_client.close()
                return {
                    "company_id": company_id,
                    "domain": company_domain,
                    "chunks_embedded": len(raw_chunks),
                    "new_embeddings": 0,
                    "skipped_embeddings": len(raw_chunks),
                    "status": "completed",
                    "message": "All chunks already embedded"
                }

            # Generate embeddings and add to MongoDB
            from openai import OpenAI
            from datetime import datetime
            import time
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # Process in batches of 100
            batch_size = 100
            total_embedded = 0

            for i in range(0, len(chunks_to_embed), batch_size):
                batch = chunks_to_embed[i:i+batch_size]
                texts = [chunk["content"] for chunk in batch]

                # Generate embeddings
                response = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts
                )
                
                # Sleep to avoid rate limits
                time.sleep(2.0)

                # Prepare MongoDB documents
                embedding_docs = []
                for chunk, emb_data in zip(batch, response.data):
                    embedding_doc = {
                        "chunk_id": chunk["chunk_id"],
                        "domain": chunk["domain"],
                        "collection_name": chunk["collection_name"],
                        "content": chunk["content"],
                        "embedding": emb_data.embedding,
                        "content_hash": chunk["content_hash"],
                        "tokens": chunk["tokens"],
                        "url": chunk.get("url"),
                        "title": chunk.get("title"),
                        "metadata": chunk.get("metadata", {}),
                        "embedded_at": datetime.utcnow()
                    }
                    embedding_docs.append(embedding_doc)

                # Insert into MongoDB
                if embedding_docs:
                    mongo_db.rag_embeddings.insert_many(embedding_docs)

                total_embedded += len(batch)
                print(f"[{company_domain}] Embedded batch {i//batch_size + 1}: {total_embedded}/{len(chunks_to_embed)} chunks")

            embedding_stats = {
                "new_embeddings": total_embedded,
                "skipped_embeddings": len(raw_chunks) - total_embedded
            }

            print(f"[{company_domain}] Embedding complete: {embedding_stats.get('new_embeddings', 0)} new chunks")

            # Close MongoDB connection
            mongo_client.close()

            # Update company embedded_at timestamp in MongoDB
            mongo_client_update = MongoClient(mongo_uri.rsplit("/", 1)[0] if "/" in mongo_uri and mongo_uri.split("/")[-1] else mongo_uri)
            mongo_db_update = mongo_client_update[db_name]
            mongo_db_update.companies.update_one(
                {"_id": ObjectId(mongo_id_str)},
                {"$set": {"embedded_at": datetime.utcnow()}}
            )
            mongo_client_update.close()

            return {
                "company_id": str(mongo_id_str),
                "domain": company_domain,
                "pages_found": len(pages),
                "products_found": len(products),
                "chunks_embedded": total_embedded,
                "new_embeddings": total_embedded,
                "skipped_embeddings": len(raw_chunks) - total_embedded,
                "status": "completed",
                "message": f"Embedded {total_embedded} new chunks from pages, products, and company data into MongoDB RAG" if total_embedded > 0 else "All chunks already embedded"
            }
        except Exception as e:
            print(f"[{company_domain}] Error during embedding: {e}")
            import traceback
            traceback.print_exc()

            # Close MongoDB connection if it exists
            try:
                mongo_client.close()
            except:
                pass

            # Still update embedded_at to avoid re-attempting immediately
            # Note: 'company' variable is not available here, it was 'company_doc' dict
            # We need to update using pymongo directly
            try:
                mongo_client_fail = MongoClient(mongo_uri.rsplit("/", 1)[0] if "/" in mongo_uri and mongo_uri.split("/")[-1] else mongo_uri)
                mongo_db_fail = mongo_client_fail[db_name]
                mongo_db_fail.companies.update_one(
                    {"_id": ObjectId(mongo_id_str)},
                    {"$set": {"embedded_at": datetime.utcnow()}}
                )
                mongo_client_fail.close()
            except:
                pass

            return {
                "company_id": str(mongo_id_str),
                "domain": company_domain,
                "chunks_embedded": 0,
                "status": "error",
                "error": str(e)
            }

    except Exception as e:
        print(f"Error embedding data for company {company_id}: {e}")
        raise


@celery_app.task(name="backend.celery_app.tasks.verify_emails_task")
def verify_emails_task(emails: List[str]) -> Dict[str, Any]:
    """
    Task to verify a list of email addresses.

    Args:
        emails: List of email addresses to verify

    Returns:
        Dictionary with verification results
    """
    # TODO: Implement email verification logic using services
    # from ..app.services.email import email_verifier
    # results = email_verifier.verify_emails(emails)

    return {
        "total": len(emails),
        "valid": 0,
        "invalid": 0,
        "results": []
    }


@celery_app.task(name="backend.celery_app.tasks.revet_domains_task", soft_time_limit=23*60*60, base=DatabaseTask, bind=True)
def revet_domains_task(
    self: Task,
    job_id: str,
    domains: List[str],
    user_id: int,
    min_ecommerce_keywords: int = 1,
    min_relevance_score: float = 0.2
) -> Dict[str, Any]:
    """
    Task to re-vet failed/rejected domains.

    This allows re-running vetting on domains that:
    - Failed due to fetch errors
    - Were rejected but might pass with different criteria
    - Need to be re-evaluated

    Args:
        job_id: Job ID for tracking
        domains: List of domains to re-vet
        user_id: User ID who initiated the re-vetting
        min_ecommerce_keywords: Minimum e-commerce keywords required (default: 1)
        min_relevance_score: Minimum relevance score (default: 0.2)

    Returns:
        Dictionary with re-vetting results
    """
    import asyncio
    from app.services.vetting.enhanced_vet import vet_domains_batch, generate_keyword_variants_ai
    from app.crud import jobs as crud_jobs
    from app.schemas.job import JobStatus
    from app.core.event_bus import event_bus
    from app.db.mongodb_models import DiscoveredDomain, Company
    from datetime import datetime

    db = self.db

    try:
        # Update job status to running
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.RUNNING,
            progress=10
        )

        # Publish job started event
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_started",
                {"job_id": job_id, "job_type": "revet"},
                user_id=str(user_id)
            ))

        # Get original discovery job keywords for vetting context
        # Try to get keywords from the most recent discovery job
        job = crud_jobs.get_job(db, job_id)

        # Parse config JSON if it's a string
        import json
        config = job.config
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}

        original_keywords = config.get("keywords", ["goalkeeper gloves"])  # Fallback

        # Generate keyword variants for vetting
        keyword_variants = asyncio.run(generate_keyword_variants_ai(original_keywords))

        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.RUNNING,
            progress=30
        )

        # Re-vet the domains
        approved_domains, rejected_domains = asyncio.run(
            vet_domains_batch(
                domains=domains,
                search_keywords=original_keywords,
                min_ecommerce_keywords=min_ecommerce_keywords,
                min_relevance_score=min_relevance_score,
                keyword_variants=keyword_variants
            )
        )

        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.RUNNING,
            progress=70
        )

        # Save approved domains as companies
        from app.schemas.company import CompanyCreate

        saved_count = 0
        for vet_result in approved_domains:
            domain = vet_result["domain"]

            # Check if company already exists
            existing = company_crud.get_company_by_domain(db, domain)
            if not existing:
                # Create new company using schema
                company_create = CompanyCreate(
                    domain=domain,
                    user_id=user_id,
                    company_name=None,  # Will be extracted during crawling
                    description=None
                )
                company_crud.create_company(db, company_create)
                saved_count += 1

        # Prepare vetting details for result
        vetting_details = []
        for vet_result in approved_domains:
            vetting_details.append({
                "domain": vet_result["domain"],
                "status": "approved",
                "reason": vet_result["reason"],
                "relevance_score": vet_result["relevance_score"],
                "has_ecommerce": vet_result["has_ecommerce"],
                "ecommerce_keywords": vet_result["ecommerce_keywords"]
            })

        for vet_result in rejected_domains:
            vetting_details.append({
                "domain": vet_result["domain"],
                "status": "rejected",
                "reason": vet_result["reason"],
                "relevance_score": vet_result["relevance_score"],
                "has_ecommerce": vet_result["has_ecommerce"],
                "ecommerce_keywords": vet_result.get("ecommerce_keywords", [])
            })

        result = {
            "total_domains": len(domains),
            "approved_domains": len(approved_domains),
            "rejected_domains": len(rejected_domains),
            "saved_domains": saved_count,
            "vetting_details": vetting_details
        }

        # Update job with results
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            result=result
        )

        # Publish job completed event
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_completed",
                {
                    "job_id": job_id,
                    "job_type": "revet",
                    "approved_count": len(approved_domains),
                    "saved_count": saved_count
                },
                user_id=str(user_id)
            ))

        return result

    except Exception as e:
        # Update job as failed
        error_msg = str(e)
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.FAILED,
            error=error_msg
        )

        # Publish job failed event
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_failed",
                {"job_id": job_id, "job_type": "revet", "error": error_msg},
                user_id=str(user_id)
            ))

        raise


@celery_app.task(name="backend.celery_app.tasks.recrawl_domains_task", base=DatabaseTask, bind=True)
def recrawl_domains_task(
    self: Task,
    job_id: str,
    domains: List[str],
    user_id: int,
    force: bool = False,
    max_pages: int = 200,
    max_depth: int = 3
) -> Dict[str, Any]:
    """
    Task to re-crawl domains (update their data).

    This allows:
    - Refreshing data for domains that were previously crawled
    - Force re-crawling even if data exists
    - Updating outdated information

    Args:
        job_id: Job ID for tracking
        domains: List of domains to re-crawl
        user_id: User ID who initiated the re-crawl
        force: Force re-crawl even if already crawled (default: False)
        max_pages: Maximum pages to crawl per domain (default: 200)
        max_depth: Maximum crawl depth (default: 3)

    Returns:
        Dictionary with re-crawl results
    """
    import asyncio
    from app.services.crawling.crawl import crawl_domains_mongodb_only
    from app.crud import jobs as crud_jobs
    from app.schemas.job import JobStatus
    from app.core.event_bus import event_bus
    from datetime import datetime

    db = self.db

    try:
        # Update job status to running
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.RUNNING,
            progress=10
        )

        # Publish job started event
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_started",
                {"job_id": job_id, "job_type": "recrawl"},
                user_id=str(user_id)
            ))

        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.RUNNING,
            progress=30
        )

        # Crawl domains (MongoDB only, skip_crawled based on force flag)
        import asyncio
        crawl_result = asyncio.run(crawl_domains_mongodb_only(
            domains=domains,
            max_pages=max_pages,
            max_depth=max_depth,
            skip_crawled=not force,  # If force=True, don't skip crawled domains
            concurrency=5,
            max_parallel_domains=3
        ))

        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.RUNNING,
            progress=80
        )

        # Update companies with crawl results
        updated_count = 0
        for result_item in crawl_result.get("results", []):
            domain = result_item.get("domain")
            if result_item.get("success"):
                # Update company record if it exists
                company = company_crud.get_company_by_domain(db, domain)
                if company:
                    company.crawl_status = 'completed'
                    company.crawled_pages = result_item.get("pages_crawled", 0)
                    company.crawled_at = datetime.utcnow()
                    updated_count += 1

        db.commit()

        result = {
            "total_domains": len(domains),
            "crawled_domains": crawl_result.get("crawled_domains", 0),
            "skipped_domains": crawl_result.get("skipped_domains", 0),
            "total_pages": crawl_result.get("total_pages", 0),
            "updated_companies": updated_count,
            "results": crawl_result.get("results", [])
        }

        # Update job with results
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            result=result
        )

        # Publish job completed event
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_completed",
                {
                    "job_id": job_id,
                    "job_type": "recrawl",
                    "crawled_count": crawl_result.get("crawled_domains", 0),
                    "pages_count": crawl_result.get("total_pages", 0)
                },
                user_id=str(user_id)
            ))

        return result

    except Exception as e:
        # Update job as failed
        error_msg = str(e)
        crud_jobs.update_job_status(
            db,
            job_id=job_id,
            status=JobStatus.FAILED,
            error=error_msg
        )

        # Publish job failed event
        if event_bus:
            asyncio.run(event_bus.publish(
                "job_failed",
                {"job_id": job_id, "job_type": "recrawl", "error": error_msg},
                user_id=str(user_id)
            ))

        raise
