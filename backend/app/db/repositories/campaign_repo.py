"""
Campaign and Email Draft Repository
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from beanie import PydanticObjectId
from app.db.mongodb_models import Campaign, EmailDraft

# --- Campaign Operations ---

async def create_campaign(user_id: str, campaign_data: Dict[str, Any]) -> Campaign:
    campaign = Campaign(user_id=user_id, **campaign_data)
    await campaign.insert()
    return campaign

async def get_campaign(campaign_id: str) -> Optional[Campaign]:
    try:
        return await Campaign.get(PydanticObjectId(campaign_id))
    except:
        return None

async def get_campaigns_by_user(user_id: str, skip: int = 0, limit: int = 50) -> List[Campaign]:
    return await Campaign.find(
        Campaign.user_id == user_id
    ).sort("-created_at").skip(skip).limit(limit).to_list()

async def update_campaign(campaign_id: str, update_data: Dict[str, Any]) -> Optional[Campaign]:
    campaign = await get_campaign(campaign_id)
    if not campaign:
        return None
    
    update_data['updated_at'] = datetime.utcnow()
    await campaign.set(update_data)
    return campaign

async def delete_campaign(campaign_id: str) -> bool:
    campaign = await get_campaign(campaign_id)
    if not campaign:
        return False
    
    # Also delete associated drafts? Optional logic.
    # For now, just delete campaign.
    await campaign.delete()
    return True

# --- EmailDraft Operations ---

async def create_draft(user_id: str, draft_data: Dict[str, Any]) -> EmailDraft:
    draft = EmailDraft(user_id=user_id, **draft_data)
    await draft.insert()
    return draft

async def get_draft(draft_id: str) -> Optional[EmailDraft]:
    try:
        return await EmailDraft.get(PydanticObjectId(draft_id))
    except:
        return None

async def get_drafts_by_campaign(campaign_id: str) -> List[EmailDraft]:
    return await EmailDraft.find(
        EmailDraft.campaign_id == campaign_id
    ).sort("-created_at").to_list()

async def get_draft_by_company(company_id: str) -> Optional[EmailDraft]:
    # Returns most recent draft for company
    return await EmailDraft.find(
        EmailDraft.company_id == company_id
    ).sort("-created_at").first_or_none()

async def update_draft(draft_id: str, update_data: Dict[str, Any]) -> Optional[EmailDraft]:
    draft = await get_draft(draft_id)
    if not draft:
        return None
    
    update_data['updated_at'] = datetime.utcnow()
    await draft.set(update_data)
    return draft
