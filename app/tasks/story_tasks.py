from app.celery_app import celery_app
from app.agents.graph import run_story_generation
from app.agents.state import StoryState
from app.models.story import StoryJob, JobStatus
from app.db.session import SessionLocal
from app.config import settings
from dotenv import load_dotenv
from typing import Dict, Any
import uuid
import asyncio
import redis
import json
import logging

# Load .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Redis client for status caching
redis_client = redis.from_url(settings.redis_url)


def update_job_status_redis(job_id: str, status: str, error: str = None):
    """Update job status in Redis cache for fast polling"""
    cache_key = f"job_status:{job_id}"
    cache_data = {
        "status": status,
        "error": error,
    }
    redis_client.setex(
        cache_key,
        3600,  # 1 hour TTL
        json.dumps(cache_data),
    )


def update_job_status_db(job_id: str, status: JobStatus, error: str = None):
    """Update job status in database using sync SQLAlchemy"""
    db = SessionLocal()
    try:
        job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
        if job:
            job.status = status
            if error:
                job.error_message = error
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True, name="generate_story_task")
def generate_story_task(self, job_id: str) -> Dict[str, Any]:
    """
    Celery task to generate a story using LangGraph workflow.
    
    Args:
        job_id: UUID of the StoryJob to process
        
    Returns:
        Dict with job_id and status
    """
    task_id = self.request.id
    return asyncio.run(_generate_story_async(job_id, task_id))


async def _generate_story_async(job_id: str, task_id: str) -> Dict[str, Any]:
    """
    Async implementation of the story generation task.
    Uses sync SQLAlchemy for DB operations via the Celery task wrapper.
    """
    # Update status to processing (sync DB call from Celery task)
    update_job_status_redis(job_id, "processing")
    update_job_status_db(job_id, JobStatus.PROCESSING)
    
    # Load job data from database (sync DB call from Celery task)
    db = SessionLocal()
    try:
        job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        # Read attributes while session is open
        prompt = job.prompt
        age_group = job.age_group
        num_illustrations = job.num_illustrations
        webhook_url = job.webhook_url
    finally:
        db.close()
    
    # Prepare initial state for LangGraph
    initial_state: StoryState = {
        "job_id": job_id,
        "prompt": prompt,
        "age_group": age_group,
        "num_illustrations": num_illustrations,
        "webhook_url": webhook_url,
        "story_text": None,
        "story_title": None,
        "image_prompts": [],
        "image_urls": [],
        "image_metadata": [],
        "error": None,
    }
    
    # Run the LangGraph workflow (async)
    logger.info(f"Starting story generation for job {job_id}")
    final_state = await run_story_generation(initial_state)
    
    # Check for errors
    if final_state.get("error"):
        error_msg = final_state["error"]
        logger.error(f"Story generation failed for job {job_id}: {error_msg}")
        update_job_status_redis(job_id, "failed", error_msg)
        update_job_status_db(job_id, JobStatus.FAILED, error_msg)
        return {"job_id": job_id, "status": "failed", "error": error_msg}
    
    # Success - assembler node already saved to DB and sent webhook
    logger.info(f"Story generation completed for job {job_id}")
    update_job_status_redis(job_id, "completed")
    update_job_status_db(job_id, JobStatus.COMPLETED)
    
    return {
        "job_id": job_id,
        "status": "completed",
        "story_id": final_state.get("story_id"),
    }
