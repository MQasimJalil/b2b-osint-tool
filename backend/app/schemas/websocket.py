"""
WebSocket message schemas
These schemas mirror the TypeScript definitions in shared/types/websocket.ts
"""

from pydantic import BaseModel
from typing import Any, Optional, Literal
from datetime import datetime
from enum import Enum


class WebSocketEventType(str, Enum):
    """WebSocket event types"""
    JOB_STARTED = "job_started"
    JOB_PROGRESS = "job_progress"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    COMPANY_UPDATED = "company_updated"
    COMPANY_LOCKED = "company_locked"
    COMPANY_UNLOCKED = "company_unlocked"
    NOTIFICATION = "notification"
    USER_ACTIVITY = "user_activity"
    CAMPAIGN_UPDATED = "campaign_updated"
    EMAIL_DRAFT_UPDATED = "email_draft_updated"


class WebSocketMessage(BaseModel):
    """Base WebSocket message structure"""
    event: WebSocketEventType
    data: Any
    user_id: Optional[str] = None
    timestamp: datetime = datetime.utcnow()

    class Config:
        use_enum_values = True


# Event-specific data schemas
class JobStartedData(BaseModel):
    job_id: str
    job_type: str


class JobProgressData(BaseModel):
    job_id: str
    progress: int  # 0-100
    status_message: Optional[str] = None


class JobCompletedData(BaseModel):
    job_id: str
    job_type: str
    result: Optional[Any] = None
    domain_count: Optional[int] = None


class JobFailedData(BaseModel):
    job_id: str
    job_type: str
    error: str


class CompanyUpdatedData(BaseModel):
    company_id: str
    status: Optional[str] = None
    enriched_at: Optional[datetime] = None
    fields_updated: Optional[list[str]] = None


class CompanyLockedData(BaseModel):
    company_id: str
    locked_by_user_id: str
    locked_by_user_name: Optional[str] = None


class CompanyUnlockedData(BaseModel):
    company_id: str


class NotificationData(BaseModel):
    id: str
    type: Literal["info", "success", "warning", "error"]
    title: str
    message: str
    action_url: Optional[str] = None


class UserActivityData(BaseModel):
    user_id: str
    user_name: str
    action: str
    resource_type: str
    resource_id: str
    description: str


class CampaignUpdatedData(BaseModel):
    campaign_id: str
    status: Optional[str] = None
    generated_count: Optional[int] = None
    sent_count: Optional[int] = None


class EmailDraftUpdatedData(BaseModel):
    draft_id: str
    company_id: str
    status: Optional[str] = None
    gmail_draft_id: Optional[str] = None
