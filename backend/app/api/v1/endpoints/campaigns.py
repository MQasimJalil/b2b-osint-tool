"""
Campaign Management API
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from ....core.security import get_current_active_user
from ....db.session import get_db
from ....db.mongodb_session import init_db
from ....crud import users as user_crud
from ....schemas import campaign as schemas
from ....db.repositories import campaign_repo, company_repo

router = APIRouter()

# --- Campaigns ---

@router.get("/", response_model=List[schemas.Campaign])
async def list_campaigns(
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all campaigns for the current user."""
    await init_db()
    return await campaign_repo.get_campaigns_by_user(current_user["sub"], skip, limit)

@router.post("/", response_model=schemas.Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    campaign: schemas.CampaignCreate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new outreach campaign."""
    await init_db()
    return await campaign_repo.create_campaign(current_user["sub"], campaign.model_dump())

@router.get("/{campaign_id}", response_model=schemas.Campaign)
async def get_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get specific campaign details."""
    await init_db()
    campaign = await campaign_repo.get_campaign(campaign_id)
    if not campaign or campaign.user_id != current_user["sub"]:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a campaign."""
    await init_db()
    campaign = await campaign_repo.get_campaign(campaign_id)
    if not campaign or campaign.user_id != current_user["sub"]:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    await campaign_repo.delete_campaign(campaign_id)
    return None

# --- Drafts within Campaign ---

@router.get("/{campaign_id}/drafts", response_model=List[schemas.EmailDraft])
async def list_campaign_drafts(
    campaign_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all email drafts in a campaign."""
    await init_db()
    # Verify ownership
    campaign = await campaign_repo.get_campaign(campaign_id)
    if not campaign or campaign.user_id != current_user["sub"]:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    return await campaign_repo.get_drafts_by_campaign(campaign_id)

@router.put("/drafts/{draft_id}", response_model=schemas.EmailDraft)
async def update_draft(
    draft_id: str,
    draft_update: schemas.EmailDraftUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a specific email draft."""
    await init_db()
    
    # Get draft
    draft = await campaign_repo.get_draft(draft_id)
    if not draft or draft.user_id != current_user["sub"]:
        raise HTTPException(status_code=404, detail="Draft not found or unauthorized")
    
    # Update
    updated = await campaign_repo.update_draft(draft_id, draft_update.model_dump(exclude_unset=True))
    return updated

@router.post("/{campaign_id}/generate-drafts", status_code=status.HTTP_202_ACCEPTED)
async def generate_drafts_batch(
    campaign_id: str,
    company_ids: List[str],
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Trigger AI generation for drafts for selected companies.
    """
    await init_db()

    # Check campaign ownership
    campaign = await campaign_repo.get_campaign(campaign_id)
    if not campaign or campaign.user_id != current_user["sub"]:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from celery_app.tasks import generate_email_draft_task

    created_count = 0
    for cid in company_ids:
        # Verify company exists and belongs to user
        company = await company_repo.get_company_by_id(cid)
        if company and company.user_id == current_user["sub"]:
            
            # Create a placeholder draft with 'uninitiated' status
            draft_data = {
                "company_id": str(company.id),
                "domain": company.domain,
                "campaign_id": campaign_id,
                "status": "uninitiated", 
                "subject": "",
                "body": "",
                "to_emails": [c['value'] for c in company.contacts if c['type'] == 'email'][:1] # Pick first email found
            }
            await campaign_repo.create_draft(current_user["sub"], draft_data)
            created_count += 1

    # Update campaign stats
    if created_count > 0:
        current_stats = campaign.stats
        current_stats['emails_generated'] = current_stats.get('emails_generated', 0) + created_count
        current_stats['total_companies'] = current_stats.get('total_companies', 0) + created_count
        await campaign_repo.update_campaign(campaign_id, {"stats": current_stats})

    return {"message": "Draft generation started", "count": created_count}

@router.post("/{campaign_id}/generate-selected", status_code=status.HTTP_202_ACCEPTED)
async def generate_selected_drafts(
    campaign_id: str,
    draft_ids: List[str],
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Trigger AI generation for specific selected drafts.
    """
    await init_db()

    # Check campaign ownership
    campaign = await campaign_repo.get_campaign(campaign_id)
    if not campaign or campaign.user_id != current_user["sub"]:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from celery_app.tasks import generate_email_draft_task
    
    triggered_count = 0
    
    for draft_id in draft_ids:
        # Get draft
        draft = await campaign_repo.get_draft(draft_id)
        if draft and draft.user_id == current_user["sub"] and draft.campaign_id == campaign_id:
            
            # Update status to generating
            await campaign_repo.update_draft(draft_id, {
                "status": "generating",
                "subject": "Generating subject...",
                "body": "Generating draft with AI... Please wait.",
                "last_error": None
            })
            
            # Trigger task (task takes company_id)
            generate_email_draft_task.delay(draft.company_id, draft_id=str(draft.id))
            triggered_count += 1

    return {"message": "Generation triggered", "count": triggered_count}
