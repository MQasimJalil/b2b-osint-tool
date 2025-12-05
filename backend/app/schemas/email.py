"""
Pydantic schemas for Email-related models.
Used for request/response validation and serialization.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime


class EmailVerificationBase(BaseModel):
    """Base email verification schema."""
    email: EmailStr
    is_valid: bool
    reason: Optional[str] = None


class EmailVerification(EmailVerificationBase):
    """Schema for email verification in API responses."""
    checks_json: Optional[Dict[str, bool]] = None
    mx_records: Optional[List[str]] = None
    smtp_response: Optional[str] = None
    verified_at: Optional[datetime] = None
    verification_time_seconds: Optional[float] = None

    class Config:
        from_attributes = True


class EmailDraftBase(BaseModel):
    """Base email draft schema."""
    subject_lines: List[str]
    email_body: str


class EmailDraftCreate(EmailDraftBase):
    """Schema for creating an email draft."""
    company_id: int


class EmailDraft(EmailDraftBase):
    """Schema for email draft in API responses."""
    id: int
    company_id: int
    gmail_draft_id: Optional[str] = None
    gmail_draft_created_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EmailSendRequest(BaseModel):
    """Schema for email send request."""
    to_email: EmailStr
    subject: str
    body: str
    html_body: Optional[str] = None  # HTML formatted body
    company_id: Optional[int] = None


class EmailVerifyRequest(BaseModel):
    """Schema for email verification request."""
    emails: List[EmailStr]


class EmailVerifyResponse(BaseModel):
    """Schema for email verification response."""
    results: List[EmailVerification]
    total_verified: int
    valid_count: int
    invalid_count: int
