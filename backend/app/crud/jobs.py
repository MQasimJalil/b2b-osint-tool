"""
CRUD operations for Job model.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc
import uuid
from datetime import datetime

from ..db import models
from ..schemas import job as schemas


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return f"job_{uuid.uuid4().hex[:12]}"


def create_job(db: Session, job: schemas.JobCreate, celery_task_id: Optional[str] = None) -> models.Job:
    """Create a new job."""
    import json
    job_id = generate_job_id()

    db_job = models.Job(
        id=job_id,
        user_id=job.user_id,
        job_type=job.job_type.value,
        status=schemas.JobStatus.QUEUED.value,
        progress=0,
        config=json.dumps(job.config) if isinstance(job.config, dict) else job.config,
        celery_task_id=celery_task_id
    )

    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job


def get_job(db: Session, job_id: str) -> Optional[models.Job]:
    """Get job by ID."""
    return db.query(models.Job).filter(models.Job.id == job_id).first()


def get_jobs_by_user(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    job_type: Optional[str] = None,
    status: Optional[str] = None
) -> List[models.Job]:
    """Get jobs for a user with optional filters."""
    query = db.query(models.Job).filter(models.Job.user_id == user_id)

    if job_type:
        query = query.filter(models.Job.job_type == job_type)

    if status:
        query = query.filter(models.Job.status == status)

    return query.order_by(desc(models.Job.created_at)).offset(skip).limit(limit).all()


def count_jobs_by_user(
    db: Session,
    user_id: int,
    job_type: Optional[str] = None,
    status: Optional[str] = None
) -> int:
    """Count jobs for a user with optional filters."""
    query = db.query(models.Job).filter(models.Job.user_id == user_id)

    if job_type:
        query = query.filter(models.Job.job_type == job_type)

    if status:
        query = query.filter(models.Job.status == status)

    return query.count()


def update_job(db: Session, job_id: str, job_update: schemas.JobUpdate) -> Optional[models.Job]:
    """Update job status and progress."""
    import json
    db_job = get_job(db, job_id)
    if not db_job:
        return None

    update_data = job_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # Serialize dict fields to JSON for SQLite
        if field == 'result' and isinstance(value, dict):
            value = json.dumps(value)
        setattr(db_job, field, value)

    db.commit()
    db.refresh(db_job)
    return db_job


def update_job_status(
    db: Session,
    job_id: str,
    status: schemas.JobStatus,
    progress: Optional[int] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None
) -> Optional[models.Job]:
    """Update job status with optional progress, result, or error."""
    import json

    db_job = get_job(db, job_id)
    if not db_job:
        return None

    db_job.status = status.value

    if progress is not None:
        db_job.progress = progress

    if result is not None:
        # Convert dict to JSON string for storage
        db_job.result = json.dumps(result)

    if error is not None:
        db_job.error = error

    # Update timestamps based on status
    if status == schemas.JobStatus.RUNNING and not db_job.started_at:
        db_job.started_at = datetime.utcnow()
    elif status in [schemas.JobStatus.COMPLETED, schemas.JobStatus.FAILED, schemas.JobStatus.CANCELLED]:
        db_job.completed_at = datetime.utcnow()
        if status == schemas.JobStatus.COMPLETED:
            db_job.progress = 100

    db.commit()
    db.refresh(db_job)
    return db_job


def delete_job(db: Session, job_id: str) -> bool:
    """Delete a job."""
    db_job = get_job(db, job_id)
    if not db_job:
        return False

    db.delete(db_job)
    db.commit()
    return True


def get_running_jobs(db: Session) -> List[models.Job]:
    """Get all currently running jobs."""
    return db.query(models.Job).filter(
        models.Job.status == schemas.JobStatus.RUNNING.value
    ).all()


def get_stale_jobs(db: Session, hours: int = 24) -> List[models.Job]:
    """Get jobs that have been running for too long."""
    from datetime import timedelta
    threshold = datetime.utcnow() - timedelta(hours=hours)

    return db.query(models.Job).filter(
        models.Job.status == schemas.JobStatus.RUNNING.value,
        models.Job.started_at < threshold
    ).all()
