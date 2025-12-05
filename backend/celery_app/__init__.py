"""
Celery application for background task processing.
"""
from celery import Celery
from app.core.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "b2b_osint_tool",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["celery_app.tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=24 * 60 * 60,  # 24 hours hard limit
    task_soft_time_limit=23 * 60 * 60,  # 23 hours soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# NOTE: MongoDB initialization is handled within each async task via await init_db()
# This ensures MongoDB/Beanie is initialized in the correct event loop created by asyncio.run()

# Optional: Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Example: Run cleanup task daily
    # "cleanup-old-data": {
    #     "task": "backend.celery_app.tasks.cleanup_old_data",
    #     "schedule": crontab(hour=2, minute=0),  # Run at 2:00 AM
    # },
}
