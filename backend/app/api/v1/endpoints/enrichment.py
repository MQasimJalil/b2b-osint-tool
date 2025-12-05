"""
Contact enrichment API endpoints.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ....core.security import get_current_active_user
from ....db.session import get_db
from ....crud import companies as company_crud, users as user_crud

router = APIRouter()


class EnrichmentRequest(BaseModel):
    """Request schema for enrichment."""
    company_id: int
    sources: List[str] = ["google", "linkedin", "social"]  # Which sources to use for enrichment


class EnrichmentResponse(BaseModel):
    """Response schema for enrichment."""
    task_id: str
    status: str
    message: str


@router.post("/run", response_model=EnrichmentResponse)
async def run_enrichment(
    request: EnrichmentRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Run contact enrichment for a company.
    This triggers a background Celery task.
    """
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify company ownership
    company = company_crud.get_company(db, request.company_id)
    if not company or company.user_id != user.id:
        raise HTTPException(status_code=404, detail="Company not found")

    # TODO: Import and call Celery task
    # from ....celery_app.tasks import enrich_company_contacts_task
    # task = enrich_company_contacts_task.delay(request.company_id, request.sources)

    return EnrichmentResponse(
        task_id="placeholder-task-id",  # Replace with actual task.id
        status="pending",
        message=f"Enrichment task started for company: {company.domain}"
    )


@router.get("/status/{task_id}")
async def get_enrichment_status(
    task_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get the status of an enrichment task.
    """
    # TODO: Check Celery task status
    return {
        "task_id": task_id,
        "status": "pending",
        "result": None
    }
