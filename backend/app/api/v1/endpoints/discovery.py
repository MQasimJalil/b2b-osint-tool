"""
Discovery API endpoints for finding new companies.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ....core.security import get_current_user
from ....db.session import get_db
from ....crud import jobs as crud_jobs
from ....schemas.job import Job, JobCreate, JobType, DiscoveryJobConfig

router = APIRouter()


class DiscoveryStartRequest(BaseModel):
    """Request schema for starting discovery."""
    keywords: List[str] = Field(..., min_length=1, description="List of keywords to search for")
    region: str = Field(default="US", description="Region for search results")
    search_engines: List[str] = Field(default=["google"], description="Search engines to use")
    depth: str = Field(default="fast", description="Search depth: fast, standard, deep")
    max_results: int = Field(default=100, ge=1, le=1000, description="Max results total")
    proxy_mode: str = Field(default="standard", description="Proxy mode: none, standard, residential")
    filters: Optional[Dict] = Field(default=None, description="Additional filters")


class DiscoveryStartResponse(BaseModel):
    """Response schema for discovery start."""
    job_id: str
    status: str
    message: str


@router.post("/start", response_model=DiscoveryStartResponse)
async def start_discovery(
    request: DiscoveryStartRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start a company discovery job.
    This creates a job and dispatches it to Celery for background processing.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    # Create discovery job config
    config = DiscoveryJobConfig(
        keywords=request.keywords,
        region=request.region,
        search_engines=request.search_engines,
        depth=request.depth,
        max_results=request.max_results,
        proxy_mode=request.proxy_mode,
        filters=request.filters
    )

    # Create job record
    job_create = JobCreate(
        user_id=user_id,
        job_type=JobType.DISCOVERY,
        config=config.model_dump()
    )

    # Create job record first
    job = crud_jobs.create_job(db, job_create, celery_task_id=None)

    # Import Celery task
    from celery_app.tasks import discover_companies_task

    # Dispatch to Celery with the job_id
    celery_task = discover_companies_task.delay(
        job_id=job.id,
        config=config.model_dump(),
        user_id=user_id
    )

    # Update job with Celery task ID
    job.celery_task_id = celery_task.id
    db.commit()
    db.refresh(job)

    return DiscoveryStartResponse(
        job_id=job.id,
        status=job.status,
        message=f"Discovery job started with {len(request.keywords)} keywords"
    )


@router.get("/jobs")
async def list_discovery_jobs(
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List discovery jobs for the current user.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    jobs = crud_jobs.get_jobs_by_user(
        db,
        user_id=user_id,
        skip=skip,
        limit=limit,
        job_type=JobType.DISCOVERY.value
    )

    return {
        "jobs": [Job.model_validate(job) for job in jobs],
        "total": crud_jobs.count_jobs_by_user(
            db,
            user_id=user_id,
            job_type=JobType.DISCOVERY.value
        )
    }


@router.get("/jobs/{job_id}", response_model=Job)
async def get_discovery_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get discovery job details.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    job = crud_jobs.get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    # Check ownership
    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this job"
        )

    return Job.model_validate(job)


class RevetDomainsRequest(BaseModel):
    """Request schema for re-vetting failed domains."""
    domains: List[str] = Field(..., min_length=1, description="List of domains to re-vet")
    job_id: Optional[str] = Field(None, description="Optional job ID to associate with")
    min_ecommerce_keywords: int = Field(default=1, ge=1, le=5, description="Min e-commerce keywords required")
    min_relevance_score: float = Field(default=0.2, ge=0.0, le=1.0, description="Min relevance score (0.0-1.0)")


class RevetDomainsResponse(BaseModel):
    """Response schema for re-vetting."""
    job_id: str
    status: str
    message: str
    domains_count: int


@router.post("/revet", response_model=RevetDomainsResponse)
async def revet_domains(
    request: RevetDomainsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Re-vet failed/rejected domains without going through discovery again.
    This is useful for domains that failed due to fetch errors or were rejected
    but might pass with different vetting parameters.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    # Create a job for tracking
    job_create = JobCreate(
        user_id=user_id,
        job_type=JobType.DISCOVERY,
        config={
            "operation": "revet",
            "domains": request.domains,
            "min_ecommerce_keywords": request.min_ecommerce_keywords,
            "min_relevance_score": request.min_relevance_score,
            "original_job_id": request.job_id
        }
    )

    job = crud_jobs.create_job(db, job_create, celery_task_id=None)

    # Import Celery task
    from celery_app.tasks import revet_domains_task

    # Dispatch to Celery
    celery_task = revet_domains_task.delay(
        job_id=job.id,
        domains=request.domains,
        user_id=user_id,
        min_ecommerce_keywords=request.min_ecommerce_keywords,
        min_relevance_score=request.min_relevance_score
    )

    # Update job with Celery task ID
    job.celery_task_id = celery_task.id
    db.commit()
    db.refresh(job)

    return RevetDomainsResponse(
        job_id=job.id,
        status=job.status,
        message=f"Re-vetting {len(request.domains)} domains",
        domains_count=len(request.domains)
    )


class RecrawlDomainsRequest(BaseModel):
    """Request schema for re-crawling domains."""
    domains: List[str] = Field(..., min_length=1, description="List of domains to re-crawl")
    force: bool = Field(default=False, description="Force re-crawl even if already crawled")
    max_pages: int = Field(default=200, ge=10, le=2000, description="Max pages per domain")
    max_depth: int = Field(default=3, ge=1, le=5, description="Max crawl depth")


class RecrawlDomainsResponse(BaseModel):
    """Response schema for re-crawling."""
    job_id: str
    status: str
    message: str
    domains_count: int


@router.post("/recrawl", response_model=RecrawlDomainsResponse)
async def recrawl_domains(
    request: RecrawlDomainsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Re-crawl or update crawled data for domains.
    This allows refreshing data for domains that were previously crawled.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    # Create a job for tracking
    job_create = JobCreate(
        user_id=user_id,
        job_type=JobType.DISCOVERY,
        config={
            "operation": "recrawl",
            "domains": request.domains,
            "force": request.force,
            "max_pages": request.max_pages,
            "max_depth": request.max_depth
        }
    )

    job = crud_jobs.create_job(db, job_create, celery_task_id=None)

    # Import Celery task
    from celery_app.tasks import recrawl_domains_task

    # Dispatch to Celery
    celery_task = recrawl_domains_task.delay(
        job_id=job.id,
        domains=request.domains,
        user_id=user_id,
        force=request.force,
        max_pages=request.max_pages,
        max_depth=request.max_depth
    )

    # Update job with Celery task ID
    job.celery_task_id = celery_task.id
    db.commit()
    db.refresh(job)

    return RecrawlDomainsResponse(
        job_id=job.id,
        status=job.status,
        message=f"Re-crawling {len(request.domains)} domains",
        domains_count=len(request.domains)
    )
