"""
Celery Beat configuration for scheduled tasks.
Use this if you need periodic tasks (e.g., cleanup, monitoring).
"""
from celery.schedules import crontab
from . import celery_app

# Example scheduled tasks
# celery_app.conf.beat_schedule = {
#     "cleanup-old-cache-daily": {
#         "task": "backend.celery_app.tasks.cleanup_old_cache",
#         "schedule": crontab(hour=2, minute=0),  # Run at 2:00 AM daily
#     },
#     "update-enrichment-data-weekly": {
#         "task": "backend.celery_app.tasks.update_enrichment_data",
#         "schedule": crontab(day_of_week=0, hour=3, minute=0),  # Run at 3:00 AM on Sundays
#     },
# }
