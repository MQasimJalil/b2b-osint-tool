"""
Pydantic schemas for Job model.
Used for request/response validation and serialization.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class JobType(str, Enum):
    """Job type enumeration."""
    DISCOVERY = "discovery"
    CRAWLING = "crawling"
    EXTRACTION = "extraction"
    ENRICHMENT = "enrichment"
    EMAIL_GENERATION = "email_generation"
    RAG_EMBEDDING = "rag_embedding"


class JobStatus(str, Enum):
    """Job status enumeration."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobBase(BaseModel):
    """Base job schema with common attributes."""
    job_type: JobType
    config: Dict[str, Any] = Field(default_factory=dict)


class JobCreate(JobBase):
    """Schema for creating a new job."""
    user_id: int


class JobUpdate(BaseModel):
    """Schema for updating a job."""
    status: Optional[JobStatus] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobInDB(JobBase):
    """Schema for job as stored in database."""
    id: str
    user_id: int
    status: JobStatus
    progress: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    celery_task_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @validator('result', pre=True)
    def parse_result(cls, v):
        """Parse result JSON string to dict."""
        import json
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @validator('config', pre=True)
    def parse_config(cls, v):
        """Parse config JSON string to dict."""
        import json
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v


class Job(JobInDB):
    """Schema for job in API responses."""
    pass


class JobListResponse(BaseModel):
    """Schema for paginated job list."""
    items: list[Job]
    total: int
    page: int = 1
    page_size: int = 50


class DiscoveryJobConfig(BaseModel):
    """Configuration for discovery job."""
    keywords: list[str] = Field(..., min_length=1)
    region: str = "US"
    search_engines: list[str] = Field(default=["google"])
    depth: str = "fast"  # fast, standard, deep
    max_results: int = Field(default=100, ge=1, le=1000)
    proxy_mode: str = "standard"  # none, standard, residential
    filters: Optional[Dict[str, Any]] = None


class EnrichmentJobConfig(BaseModel):
    """Configuration for enrichment job."""
    company_ids: list[str] = Field(..., min_length=1)
    enrichment_types: list[str] = Field(
        default=["contacts", "products", "social"]
    )
    deep_scan: bool = False
    linkedin_enabled: bool = False


class CrawlingJobConfig(BaseModel):
    """Configuration for crawling job."""
    company_ids: list[str] = Field(..., min_length=1)
    depth: int = Field(default=2, ge=1, le=5)
    max_pages: int = Field(default=50, ge=1, le=500)
    extract_contacts: bool = True
    extract_products: bool = True
    screenshot: bool = False


class JobProgressUpdate(BaseModel):
    """Schema for job progress updates (WebSocket)."""
    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    message: Optional[str] = None
    current_step: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
