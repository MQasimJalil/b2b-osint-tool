from typing import List, Optional, Dict, Any, Annotated
from pydantic import BaseModel, Field, BeforeValidator
from datetime import datetime

# Helper for ObjectId serialization
PyObjectId = Annotated[str, BeforeValidator(str)]

# --- Campaign Schemas ---

class CampaignBase(BaseModel):
    name: str
    type: str = "email_outreach"
    status: str = "draft"

class CampaignCreate(CampaignBase):
    pass

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    stats: Optional[Dict[str, int]] = None

class Campaign(CampaignBase):
    id: PyObjectId = Field(validation_alias="_id")
    user_id: str
    stats: Dict[str, int]
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        from_attributes = True

# --- EmailDraft Schemas ---

class EmailDraftBase(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    to_emails: List[str] = []

class EmailDraftCreate(EmailDraftBase):
    company_id: str
    campaign_id: Optional[str] = None
    domain: str

class EmailDraftUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    to_emails: Optional[List[str]] = None

class EmailDraft(EmailDraftBase):
    id: PyObjectId = Field(validation_alias="_id")
    company_id: str
    campaign_id: Optional[str] = None
    domain: str
    user_id: str
    status: str
    subject_line_options: List[str] = []
    last_error: Optional[str] = None
    sent: bool
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        from_attributes = True