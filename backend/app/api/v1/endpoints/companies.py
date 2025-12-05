"""
Company management API endpoints.
"""
from typing import List, Optional, Dict, Union
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from ....core.security import get_current_active_user
from ....db.session import get_db
from ....db.mongodb_session import init_db
from ....crud import companies as crud, users as user_crud
from ....schemas import company as schemas
from ....db.repositories import company_repo, crawling_repo, product_repo

router = APIRouter()


class DashboardStats(BaseModel):
    """Dashboard statistics response model."""
    total_companies: int
    companies_with_contacts: int
    total_contacts: int
    emails_sent: int = 0  # Placeholder for future implementation

class CompaniesListResponse(BaseModel):
    """Response with companies list and total count."""
    companies: List[schemas.Company]
    total: int
    skip: int
    limit: int

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get dashboard statistics for the current user."""
    await init_db()
    user_id = current_user["sub"] # Auth0 ID

    # Use MongoDB for stats to match the visible list
    total_companies = await company_repo.count_companies_by_user(user_id)
    companies_with_contacts = await company_repo.count_companies_with_contacts(user_id)
    total_contacts = await company_repo.count_total_contacts(user_id)

    return DashboardStats(
        total_companies=total_companies,
        companies_with_contacts=companies_with_contacts,
        total_contacts=total_contacts,
        emails_sent=0  # TODO: Implement email tracking
    )


@router.get("/", response_model=CompaniesListResponse)
async def list_companies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None,
    only_embedded: bool = Query(False, description="Only show companies with embedded data"),
    crawled_status_filter: Optional[str] = Query(None, description="Filter by crawled status: 'all', 'crawled_only'"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List companies for the current user."""
    await init_db()
    user_id = current_user["sub"]

    # Determine filter for crawled companies
    crawled_only_filter = crawled_status_filter == "crawled_only"

    # Get all companies (user can mark as irrelevant or delete manually)
    if search:
        # Search currently ignores only_embedded flag (TODO: update search_companies)
        companies = await company_repo.search_companies(
            user_id=user_id,
            search_query=search,
            skip=skip,
            limit=limit,
            crawled_only=crawled_only_filter # Pass filter to search if implemented
        )
        # For search, we don't have an easy way to get total count yet without extra query
        total = len(companies) # Approximation for now if search is used
    else:
        companies = await company_repo.get_companies_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit,
            only_embedded=only_embedded,
            crawled_only=crawled_only_filter
        )
        # Get total count (all companies)
        total = await company_repo.count_companies_by_user(
            user_id=user_id, 
            only_embedded=only_embedded,
            crawled_only=crawled_only_filter
        )

    # Get crawl status for all companies
    domains = [c.domain for c in companies]
    crawl_status_map = await crawling_repo.get_crawl_status_batch(domains) if domains else {}

    # Convert to response model
    company_responses = []
    for company in companies:
        crawl_info = crawl_status_map.get(company.domain, {})

        # Determine crawl status
        if crawl_info.get("fully_crawled"):
            crawl_status = "completed"
        elif crawl_info.get("in_progress"):
            crawl_status = "crawling"
        elif crawl_info.get("pages", 0) > 0:
            crawl_status = "completed"  # Has pages but not marked complete
        else:
            crawl_status = "not_crawled"
        
        # Map Mongo fields to Schema
        # Note: Mongo Company ID is ObjectId, Schema expects String ID.
        # If SQL ID is needed for other things, we might have a mismatch, 
        # but for display we use Mongo data.
        
        # We try to map as close as possible to schemas.Company
        # Ideally, schemas.Company should be flexible enough.
        
        comp_dict = {
            "id": str(company.id),
            "domain": company.domain,
            "company_name": company.company_name,
            "description": company.description,
            "contacts": company.contacts or [],
            "social_media": company.social_media or [],
            "user_id": 0, # Legacy SQL field, fill dummy or try to match SQL? 
                          # Ideally we transition fully to Mongo IDs for frontend.
            "created_at": company.created_at,
            "updated_at": company.updated_at,
            "crawl_status": crawl_status,
            "crawled_pages": crawl_info.get("pages", 0),
            # Add other fields if schema requires them, defaulting to None/Empty
             "smykm_notes": [], 
             "products": [],
             "contact_score": 0.0,
             "search_mode": "discovery",
             "vetting_status": "approved", # Assumed if in list
             "vetting_score": 0.0,
             "vetting_details": None,
             "vetted_at": None,
             "crawl_progress": 0,
             "crawled_at": None,
             "extracted_at": company.extracted_at,
             "embedded_at": company.embedded_at,
             "enriched_at": company.enriched_at,
        }
        company_responses.append(comp_dict)

    return CompaniesListResponse(
        companies=company_responses,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/by-domain/{domain}", response_model=schemas.CompanyWithRelations)
async def get_company_by_domain(
    domain: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific company by domain or base name with all related data from MongoDB."""
    # Initialize MongoDB
    await init_db()

    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get detailed data from MongoDB directly
    mongo_company = await company_repo.get_company_by_domain(domain)
    
    if not mongo_company:
         # Try prefix match (fuzzy search) if exact match fails
         # This handles cases where frontend sends 'advantagegk' but domain is 'advantagegk.com'
         mongo_company = await company_repo.get_company_by_domain_prefix(domain)
    
    if not mongo_company:
         # Fallback to SQL check if not in Mongo (shouldn't happen if synced)
         pg_company = crud.get_company_by_domain(db, domain)
         if not pg_company:
             raise HTTPException(status_code=404, detail="Company not found")
         if pg_company.user_id != user.id:
             raise HTTPException(status_code=403, detail="Not authorized")
         # If only in SQL, return SQL data
         return pg_company
    
    # Verify ownership in Mongo (using string Auth0 ID)
    if mongo_company.user_id != current_user["sub"]:
         raise HTTPException(status_code=403, detail="Not authorized to access this company")

    # Return Mongo data adapted to Schema
    # Get crawl status
    crawl_state = await crawling_repo.get_crawl_state(mongo_company.domain)
    crawl_status = "not_crawled"
    crawled_pages = 0
    crawled_at = None
    
    if crawl_state:
        if crawl_state.is_complete:
            crawl_status = "completed"
        elif crawl_state.pages_crawled > 0:
            crawl_status = "crawling" # Or "in_progress"
        
        crawled_pages = crawl_state.pages_crawled
        # Use completed_at or started_at
        crawled_at = crawl_state.completed_at or crawl_state.started_at

    return {
        "id": str(mongo_company.id),
        "user_id": user.id, # Return SQL ID for consistency with other tools?
        "domain": mongo_company.domain,
        "company_name": mongo_company.company_name,
        "description": mongo_company.description,
        "contacts": mongo_company.contacts or [],
        "social_media": mongo_company.social_media or [],
        "created_at": mongo_company.created_at,
        "updated_at": mongo_company.updated_at,
        "extracted_at": mongo_company.extracted_at,
        "enriched_at": mongo_company.enriched_at,
        "embedded_at": mongo_company.embedded_at,
        "smykm_notes": mongo_company.smykm_notes or [],
        "contact_score": mongo_company.contact_score or 0.0,
        "search_mode": mongo_company.search_mode or "discovery",
        "products": [],
        "crawl_status": crawl_status,
        "crawled_pages": crawled_pages,
        "crawled_at": crawled_at,
    }


@router.get("/{company_id}", response_model=schemas.CompanyWithRelations)
def get_company(
    company_id: int,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific company with all related data."""
    # Legacy SQL ID support
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    company = crud.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Verify ownership
    if company.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this company")

    return company


@router.post("/", response_model=schemas.Company, status_code=status.HTTP_201_CREATED)
async def create_company(
    company: schemas.CompanyCreate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new company in both SQL and MongoDB."""
    await init_db()
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if domain already exists (SQL)
    existing = crud.get_company_by_domain(db, company.domain)
    if existing:
        raise HTTPException(status_code=400, detail="Company with this domain already exists")

    # 1. Create in SQL
    company.user_id = user.id # Set internal integer ID
    sql_company = crud.create_company(db, company)
    
    # 2. Create in MongoDB
    mongo_data = {
        "user_id": current_user["sub"], # Auth0 ID
        "domain": company.domain,
        "company_name": company.company_name,
        "description": company.description,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    await company_repo.create_company(mongo_data)

    return sql_company


@router.put("/{company_id}", response_model=schemas.Company)
def update_company(
    company_id: int,
    company_update: schemas.CompanyUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a company (SQL only for now, TODO: Sync to Mongo)."""
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    company = crud.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Verify ownership
    if company.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this company")

    updated = crud.update_company(db, company_id, company_update)
    return updated


@router.delete("/{company_id_or_domain}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id_or_domain: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a company from both SQL and MongoDB. Accepts ID or Domain."""
    await init_db()
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    domain_to_delete = None
    
    # Try to parse as Integer ID first (SQL style)
    if company_id_or_domain.isdigit():
        company_id = int(company_id_or_domain)
        company = crud.get_company(db, company_id)
        if company:
            if company.user_id != user.id:
                raise HTTPException(status_code=403, detail="Not authorized")
            domain_to_delete = company.domain
            crud.delete_company(db, company_id)
    else:
        # Assume it is a domain or Mongo ID (but we primarily use domain for Mongo lookups)
        # Try finding by domain in SQL to delete there too
        domain_to_delete = company_id_or_domain
        company = crud.get_company_by_domain(db, domain_to_delete)
        if company:
            if company.user_id != user.id:
                 raise HTTPException(status_code=403, detail="Not authorized")
            crud.delete_company(db, company.id)

    # Delete from MongoDB
    if domain_to_delete:
        # Delete related Mongo data
        await crawling_repo.delete_crawled_pages_by_domain(domain_to_delete)
        await product_repo.delete_products_by_domain(domain_to_delete)
        await company_repo.delete_company(domain_to_delete)
    
    return None


@router.get("/{company_id}/contacts", response_model=List[schemas.Contact])
async def get_company_contacts(
    company_id: int,
    contact_type: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get contacts for a company from MongoDB."""
    # Initialize MongoDB
    await init_db()

    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get company from PostgreSQL to verify ownership
    company = crud.get_company(db, company_id)
    if not company or company.user_id != user.id:
        raise HTTPException(status_code=404, detail="Company not found")

    # Get contacts from MongoDB
    mongo_company = await company_repo.get_company_by_domain(company.domain)
    if not mongo_company or not mongo_company.contacts:
        return []

    # Filter by contact type if specified
    contacts = mongo_company.contacts
    if contact_type:
        contacts = [c for c in contacts if c.get("type") == contact_type]

    return contacts


@router.post("/{company_id}/contacts", response_model=schemas.Contact, status_code=status.HTTP_201_CREATED)
def create_contact(
    company_id: int,
    contact: schemas.ContactBase,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a contact for a company."""
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    company = crud.get_company(db, company_id)
    if not company or company.user_id != user.id:
        raise HTTPException(status_code=404, detail="Company not found")

    contact_create = schemas.ContactCreate(company_id=company_id, **contact.model_dump())
    return crud.create_contact(db, contact_create)


@router.get("/{company_id}/enrichment-history", response_model=List[schemas.EnrichmentHistory])
def get_enrichment_history(
    company_id: int,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get enrichment history for a company."""
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    company = crud.get_company(db, company_id)
    if not company or company.user_id != user.id:
        raise HTTPException(status_code=404, detail="Company not found")

    return crud.get_company_enrichment_history(db, company_id)


@router.post("/{company_id}/crawl", status_code=status.HTTP_202_ACCEPTED)
async def crawl_company(
    company_id: Union[str, int],
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Trigger crawling for a specific company (MongoDB only storage).
    """
    from celery_app.tasks import crawl_company_website_task
    await init_db()

    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find company
    domain = None
    company_obj = None
    
    # Try Mongo first (preferred)
    mongo_company = await company_repo.get_company_by_id(str(company_id))
    if mongo_company:
        if mongo_company.user_id != current_user["sub"]:
            raise HTTPException(status_code=403, detail="Not authorized")
        domain = mongo_company.domain
        company_obj = mongo_company
    
    # Fallback to SQL
    if not domain and (isinstance(company_id, int) or (isinstance(company_id, str) and company_id.isdigit())):
        sql_company = crud.get_company(db, int(company_id))
        if sql_company:
            if sql_company.user_id != user.id:
                raise HTTPException(status_code=403, detail="Not authorized")
            domain = sql_company.domain
            # We should ideally have a Mongo record too, but if not, task will handle it?
            # Task expects Mongo ID usually.
            # Actually task uses `get_company` which might use SQL or Mongo?
            # Let's check task.
            
    if not domain:
        raise HTTPException(status_code=404, detail="Company not found")

    # Reset crawl state in Mongo
    await crawling_repo.update_crawl_state(domain, is_complete=False, pages_crawled=0)
    
    # Also update SQL metadata if available
    # (Skipping mixed mode complexity for now, focusing on Mongo state which frontend uses)

    # Trigger Celery task
    # Pass the ID we have; the task should be smart enough to handle ID or Domain?
    # Ideally pass DOMAIN to task for robustness?
    # For now, pass ID as string.
    task = crawl_company_website_task.delay(str(company_id))

    return {
        "message": "Crawl started",
        "company_id": company_id,
        "domain": domain,
        "task_id": task.id,
        "status": "queued"
    }


@router.post("/crawl/batch", status_code=status.HTTP_202_ACCEPTED)
async def crawl_companies_batch(
    company_ids: List[Union[str, int]],
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Trigger crawling for multiple companies in batch.
    """
    from celery_app.tasks import crawl_companies_batch_task
    await init_db()

    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not company_ids:
        raise HTTPException(status_code=400, detail="No company IDs provided")

    # Validate existence? Or let task handle errors?
    # For batch, we assume valid IDs.
    
    # Reset crawl states for all (best effort)
    # This requires iterating and finding domains.
    # Defer to background task for speed.

    # Trigger batch Celery task
    # Convert all to strings
    ids_str = [str(cid) for cid in company_ids]
    task = crawl_companies_batch_task.delay(ids_str, user.id)

    return {
        "message": f"Batch crawl started for {len(company_ids)} companies",
        "company_ids": company_ids,
        "task_id": task.id,
        "status": "queued"
    }


@router.post("/{company_id}/extract", status_code=status.HTTP_202_ACCEPTED)
async def extract_company_data(
    company_id: Union[str, int],
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Trigger data extraction for a specific company (from existing crawled data).
    """
    from celery_app.tasks import extract_company_data_task
    await init_db()

    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find company (Mongo preferred)
    domain = None
    mongo_company = await company_repo.get_company_by_id(str(company_id))
    
    if mongo_company:
        if mongo_company.user_id != current_user["sub"]:
             raise HTTPException(status_code=403, detail="Not authorized")
        domain = mongo_company.domain
    else:
        # Fallback SQL
        if isinstance(company_id, int) or (isinstance(company_id, str) and company_id.isdigit()):
            sql_company = crud.get_company(db, int(company_id))
            if sql_company:
                if sql_company.user_id != user.id:
                    raise HTTPException(status_code=403, detail="Not authorized")
                domain = sql_company.domain

    if not domain:
        raise HTTPException(status_code=404, detail="Company not found")

    # Trigger Extraction Task
    task = extract_company_data_task.delay(str(company_id))

    return {
        "message": "Extraction started",
        "company_id": company_id,
        "domain": domain,
        "task_id": task.id,
        "status": "queued"
    }


@router.post("/{company_id}/embed", status_code=status.HTTP_202_ACCEPTED)
async def embed_company_data(
    company_id: Union[str, int],
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Trigger RAG embedding for a specific company.
    """
    from celery_app.tasks import embed_company_rag_task
    await init_db()

    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Trigger Embedding Task
    task = embed_company_rag_task.delay(str(company_id))

    return {
        "message": "Embedding started",
        "company_id": company_id,
        "task_id": task.id,
        "status": "queued"
    }


@router.get("/{company_id}/crawl-status")
def get_crawl_status(
    company_id: int,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get the current crawl status for a company.
    """
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    company = crud.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Verify ownership
    if company.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this company")

    return {
        "company_id": company_id,
        "domain": company.domain,
        "crawl_status": company.crawl_status,
        "crawl_progress": company.crawl_progress,
        "crawled_pages": company.crawled_pages,
        "crawled_at": company.crawled_at.isoformat() if company.crawled_at else None,
        "extracted_at": company.extracted_at.isoformat() if company.extracted_at else None,
        "embedded_at": company.embedded_at.isoformat() if company.embedded_at else None
    }