"""
Job status and management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from ....core.security import get_current_user
from ....db.session import get_db
from ....crud import jobs as crud_jobs
from ....schemas.job import (
    Job, JobListResponse, JobStatus, JobType
)
from ....core.exceptions import ResourceNotFound

router = APIRouter()


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    job_type: Optional[JobType] = Query(None, description="Filter by job type"),
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all jobs for the current user.

    Supports filtering by job type and status, with pagination.

    Args:
        job_type: Optional filter by job type
        status: Optional filter by status
        page: Page number (1-indexed)
        page_size: Number of items per page
        current_user: Current authenticated user
        db: Database session

    Returns:
        Paginated list of jobs
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    skip = (page - 1) * page_size

    # Get jobs
    jobs = crud_jobs.get_jobs_by_user(
        db,
        user_id=user_id,
        skip=skip,
        limit=page_size,
        job_type=job_type.value if job_type else None,
        status=status.value if status else None
    )

    # Get total count
    total = crud_jobs.count_jobs_by_user(
        db,
        user_id=user_id,
        job_type=job_type.value if job_type else None,
        status=status.value if status else None
    )

    return JobListResponse(
        items=[Job.model_validate(job) for job in jobs],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{job_id}", response_model=Job)
async def get_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get job details by ID.

    Args:
        job_id: Job ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Job details

    Raises:
        HTTPException: If job not found or not owned by user
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    job = crud_jobs.get_job(db, job_id)
    if not job:
        raise ResourceNotFound("Job", job_id)

    # Check ownership
    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this job"
        )

    return Job.model_validate(job)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cancel a running job.

    Args:
        job_id: Job ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If job not found, not owned by user, or cannot be cancelled
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    job = crud_jobs.get_job(db, job_id)
    if not job:
        raise ResourceNotFound("Job", job_id)

    # Check ownership
    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to cancel this job"
        )

    # Check if job can be cancelled
    if job.status not in [JobStatus.QUEUED.value, JobStatus.RUNNING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status: {job.status}"
        )

    # Cancel the Celery task if it exists
    if job.celery_task_id:
        try:
            from celery import current_app as celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=True)
        except Exception as e:
            print(f"Error cancelling Celery task: {e}")

    # Update job status
    updated_job = crud_jobs.update_job_status(
        db,
        job_id=job_id,
        status=JobStatus.CANCELLED,
        error="Cancelled by user"
    )

    return {
        "message": "Job cancelled successfully",
        "job_id": job_id,
        "status": updated_job.status
    }


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a job record.

    Args:
        job_id: Job ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If job not found or not owned by user
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    job = crud_jobs.get_job(db, job_id)
    if not job:
        raise ResourceNotFound("Job", job_id)

    # Check ownership
    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this job"
        )

    # Don't allow deletion of running jobs
    if job.status == JobStatus.RUNNING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a running job. Cancel it first."
        )

    success = crud_jobs.delete_job(db, job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete job"
        )

    return {
        "message": "Job deleted successfully",
        "job_id": job_id
    }
