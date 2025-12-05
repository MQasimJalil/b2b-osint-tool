"""
Pydantic schemas for Company model.
Used for request/response validation and serialization.
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any, Union
from datetime import datetime


class ContactBase(BaseModel):
    """Base contact schema."""
    type: str  # email, phone, whatsapp, address, contact_page
    value: str
    source: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    is_primary: bool = False


class ContactCreate(ContactBase):
    """Schema for creating a contact."""
    company_id: Union[str, int]


class Contact(ContactBase):
    """Schema for contact in API responses."""
    id: Union[str, int, None] = None
    company_id: Union[str, int, None] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SocialMediaBase(BaseModel):
    """Base social media schema."""
    platform: str
    url: str
    source: Optional[str] = None


class SocialMediaCreate(SocialMediaBase):
    """Schema for creating a social media profile."""
    company_id: Union[str, int]


class SocialMedia(SocialMediaBase):
    """Schema for social media in API responses."""
    id: Union[str, int, None] = None
    company_id: Union[str, int, None] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompanyBase(BaseModel):
    """Base company schema."""
    domain: str
    company_name: Optional[str] = None
    description: Optional[str] = None
    smykm_notes: Optional[List[str]] = None
    contact_score: Optional[float] = None
    search_mode: Optional[str] = None


class CompanyCreate(CompanyBase):
    """Schema for creating a company."""
    user_id: Union[str, int]


class CompanyUpdate(BaseModel):
    """Schema for updating a company."""
    company_name: Optional[str] = None
    description: Optional[str] = None
    smykm_notes: Optional[List[str]] = None
    contact_score: Optional[float] = None
    search_mode: Optional[str] = None


class Company(CompanyBase):
    """Schema for company in API responses."""
    id: Union[str, int]
    user_id: Union[str, int]

    # Vetting fields
    vetting_status: Optional[str] = None  # pending, approved, rejected
    vetting_score: Optional[float] = None  # 0.0-1.0 keyword relevance score
    vetting_details: Optional[str] = None  # JSON with vetting details
    vetted_at: Optional[datetime] = None

    # Crawl fields
    crawl_status: Optional[str] = None  # not_crawled, queued, crawling, completed, failed
    crawl_progress: Optional[int] = None  # 0-100
    crawled_pages: Optional[int] = None  # Number of pages crawled
    crawled_at: Optional[datetime] = None

    # Relevance fields (for filtering companies with no relevant products)
    relevance_status: Optional[str] = None  # pending, relevant, irrelevant
    relevance_reason: Optional[str] = None  # Reason for marking as irrelevant

    # Extraction and embedding
    extracted_at: Optional[datetime] = None
    embedded_at: Optional[datetime] = None
    enriched_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CompanyWithRelations(Company):
    """Schema for company with all related data."""
    contacts: List[Contact] = []
    social_media: List[SocialMedia] = []

    class Config:
        from_attributes = True


class EnrichmentHistoryBase(BaseModel):
    """Base enrichment history schema."""
    source: str
    status: str  # success, failure
    details: Optional[Dict[str, Any]] = None


class EnrichmentHistoryCreate(EnrichmentHistoryBase):
    """Schema for creating enrichment history."""
    company_id: Union[str, int]


class EnrichmentHistory(EnrichmentHistoryBase):
    """Schema for enrichment history in API responses."""
    id: Union[str, int]
    company_id: Union[str, int]
    enriched_at: datetime

    class Config:
        from_attributes = True
