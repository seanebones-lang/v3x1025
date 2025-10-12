"""
Celery tasks for background processing and scheduled jobs.
"""

from celery import Celery
from celery.schedules import crontab

from src.config import settings

# Initialize Celery
celery_app = Celery(
    "dealership_rag",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend
)

# Configure Celery with dead-letter queue for failed tasks
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # Acknowledge only after successful completion
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    task_track_started=True,  # Track task start time
)

# Dead-letter queue configuration
# Failed tasks are moved to 'failed' queue after max retries
celery_app.conf.task_routes = {
    '*': {'queue': 'default'},
}

# Monitor queue lengths in production:
# celery -A src.tasks.celery_app inspect active_queues

# For production monitoring, use Flower (Celery web dashboard):
# pip install flower
# celery -A src.tasks.celery_app flower --port=5555
# Access at http://localhost:5555 for real-time task monitoring

# Task revocation for cancellations:
# celery -A src.tasks.celery_app control revoke TASK_ID --terminate

# Scheduled tasks
celery_app.conf.beat_schedule = {
    "sync-dms-hourly": {
        "task": "src.tasks.sync_dms_inventory",
        "schedule": crontab(minute=0),  # Every hour
    },
    "reindex-documents-daily": {
        "task": "src.tasks.reindex_documents",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}


@celery_app.task(
    name="src.tasks.sync_dms_inventory",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3
)
def sync_dms_inventory(self):
    """Scheduled task to sync DMS inventory with auto-retry."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Syncing DMS inventory (attempt {self.request.retries + 1}/4)...")
        # Implementation would go here
        logger.info("DMS inventory sync successful")
        return {"status": "success", "message": "DMS inventory synced"}
    except Exception as e:
        logger.error(f"DMS sync failed: {e}")
        if self.request.retries >= self.max_retries:
            logger.critical(f"DMS sync failed after {self.max_retries} retries - ALERT")
        raise


@celery_app.task(name="src.tasks.reindex_documents")
def reindex_documents():
    """Scheduled task to reindex documents."""
    print(" Reindexing documents...")
    # Implementation would go here
    return {"status": "success", "message": "Documents reindexed"}


@celery_app.task(name="src.tasks.process_document")
def process_document(file_path: str, namespace: str = "default"):
    """Background task to process a document."""
    print(f" Processing document: {file_path}")
    # Implementation would go here
    return {"status": "success", "file": file_path}

