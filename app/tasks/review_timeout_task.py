"""
Celery Beat task: Auto-reject stories that have been pending review
beyond the configured SLA (review_timeout_days).

Runs periodically (e.g., every hour) and scans for expired pending reviews.
"""

from datetime import datetime, timedelta, timezone
from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.story import StoryJob, JobStatus
from app.models.review import StoryReview
from app.tasks.story_tasks import update_job_status_redis
from app.config import settings
from app.constants import REVIEW_TIMEOUT_REJECTED
import uuid
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="review_timeout_check")
def review_timeout_check():
    """
    Scan for pending_review jobs that have exceeded the timeout SLA.
    Auto-reject them with a timeout reason.
    """
    timeout_days = settings.review_timeout_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=timeout_days)

    db = SessionLocal()
    try:
        expired_jobs = (
            db.query(StoryJob)
            .filter(
                StoryJob.status == JobStatus.PENDING_REVIEW,
                StoryJob.updated_at < cutoff,
            )
            .all()
        )

        if not expired_jobs:
            logger.debug("No expired pending reviews found")
            return {"expired_count": 0}

        logger.info(f"Found {len(expired_jobs)} expired pending reviews (>{timeout_days} days)")

        for job in expired_jobs:
            job_id = str(job.id)

            # Create timeout review record
            existing_review = db.query(StoryReview).filter(
                StoryReview.job_id == job.id
            ).first()
            if not existing_review:
                db.add(StoryReview(
                    id=uuid.uuid4(),
                    job_id=job.id,
                    reviewer_id="system_timeout",
                    decision=REVIEW_TIMEOUT_REJECTED,
                    comment=f"Auto-rejected: No review received within {timeout_days} day(s)",
                    guardrail_passed=True,
                ))

            job.status = JobStatus.REJECTED
            update_job_status_redis(job_id, "rejected")

            logger.info(f"Job {job_id}: Timeout-rejected (pending since {job.updated_at})")

        db.commit()

        return {"expired_count": len(expired_jobs)}

    except Exception as e:
        db.rollback()
        logger.error(f"Review timeout check failed: {e}")
        raise
    finally:
        db.close()
