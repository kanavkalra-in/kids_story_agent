from app.celery_app import celery_app
from app.agents.graph import run_story_generation
from app.agents.state import StoryState
from app.models.story import Story, StoryImage, StoryVideo, StoryJob, JobStatus
from app.db.session import SessionLocal
from app.services.redis_client import redis_client
from app.services.webhook import send_webhook_sync
from app.agents.prompter_utils import StoryGenerationError
from app.constants import JOB_STATUS_CACHE_TTL, DEFAULT_STORY_TITLE
import uuid
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


def update_job_status_redis(job_id: str, status: str, error: str = None):
    """Update job status in Redis cache for fast polling"""
    cache_key = f"job_status:{job_id}"
    cache_data = {
        "status": status,
        "error": error,
    }
    redis_client.setex(
        cache_key,
        JOB_STATUS_CACHE_TTL,
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
def generate_story_task(self, job_id: str) -> dict[str, Any]:
    """
    Celery task to generate a story using LangGraph workflow.
    
    Args:
        job_id: UUID of the StoryJob to process
        
    Returns:
        Dict with job_id and status
    """
    task_id = self.request.id
    return asyncio.run(_generate_story_async(job_id, task_id))


async def _generate_story_async(job_id: str, task_id: str) -> dict[str, Any]:
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
        generate_images = job.generate_images
        generate_videos = job.generate_videos
        webhook_url = job.webhook_url
    finally:
        db.close()
    
    # Prepare initial state for LangGraph
    initial_state: StoryState = {
        "job_id": job_id,
        "prompt": prompt,
        "age_group": age_group,
        "num_illustrations": num_illustrations,
        "generate_images": generate_images,
        "generate_videos": generate_videos,
        "webhook_url": webhook_url,
        "story_text": None,
        "story_title": None,
        # Prompter outputs
        "image_prompts": [],
        "image_descriptions": [],
        "video_prompts": [],
        "video_descriptions": [],
        # Generator outputs (accumulated via operator.add reducers)
        "image_urls": [],
        "image_metadata": [],
        "video_urls": [],
        "video_metadata": [],
        "error": None,
    }
    
    # Run the LangGraph workflow (async)
    logger.info(f"Starting story generation for job {job_id}")
    try:
        final_state = await run_story_generation(initial_state)
    except StoryGenerationError as e:
        error_msg = str(e)
        logger.error(f"Story generation failed for job {job_id}: {error_msg}")
        update_job_status_redis(job_id, "failed", error_msg)
        update_job_status_db(job_id, JobStatus.FAILED, error_msg)
        return {"job_id": job_id, "status": "failed", "error": error_msg}
    
    # Check for errors in state
    if final_state.get("error"):
        error_msg = final_state["error"]
        logger.error(f"Story generation failed for job {job_id}: {error_msg}")
        update_job_status_redis(job_id, "failed", error_msg)
        update_job_status_db(job_id, JobStatus.FAILED, error_msg)
        return {"job_id": job_id, "status": "failed", "error": error_msg}
    
    # Extract validated results from assembler node
    story_text = final_state.get("story_text")
    story_title = final_state.get("story_title")
    image_urls = final_state.get("image_urls", [])
    image_metadata = final_state.get("image_metadata", [])
    video_urls = final_state.get("video_urls", [])
    video_metadata = final_state.get("video_metadata", [])
    
    # Persist to database and send webhook
    try:
        story_id = _persist_story_to_db(
            job_id, story_text, story_title,
            image_urls, image_metadata,
            video_urls, video_metadata,
            initial_state
        )
        
        # Send webhook if configured
        if webhook_url:
            _send_completion_webhook(webhook_url, job_id, story_id, story_text, story_title,
                                     image_urls, image_metadata, video_urls, video_metadata)
        
        logger.info(f"Story generation completed for job {job_id}")
        update_job_status_redis(job_id, "completed")
        update_job_status_db(job_id, JobStatus.COMPLETED)
        
        return {
            "job_id": job_id,
            "status": "completed",
            "story_id": story_id,
        }
    except Exception as e:
        error_msg = f"Failed to persist story to database: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}")
        update_job_status_redis(job_id, "failed", error_msg)
        update_job_status_db(job_id, JobStatus.FAILED, error_msg)
        return {"job_id": job_id, "status": "failed", "error": error_msg}


def _persist_story_to_db(
    job_id: str, story_text: str, story_title: str,
    image_urls: list, image_metadata: list,
    video_urls: list, video_metadata: list,
    state: StoryState
) -> str:
    """
    Persist story to database using sync SQLAlchemy.
    Called from Celery context, so we use sync operations.
    
    Returns:
        story_id as string
    """
    db = SessionLocal()
    try:
        job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
        if not job:
            raise StoryGenerationError(f"Job {job_id} not found")

        story = Story(
            id=uuid.uuid4(),
            job_id=job.id,
            title=story_title or DEFAULT_STORY_TITLE,
            content=story_text,
            age_group=state.get("age_group", "6-8"),
            prompt=state.get("prompt", ""),
        )
        db.add(story)
        db.flush()

        for idx, (url, metadata) in enumerate(zip(image_urls, image_metadata)):
            db.add(StoryImage(
                id=uuid.uuid4(),
                story_id=story.id,
                image_url=url,
                prompt_used=metadata.get("prompt", ""),
                scene_description=metadata.get("description", ""),
                display_order=idx,
            ))

        for idx, (url, metadata) in enumerate(zip(video_urls, video_metadata)):
            db.add(StoryVideo(
                id=uuid.uuid4(),
                story_id=story.id,
                video_url=url,
                prompt_used=metadata.get("prompt", ""),
                scene_description=metadata.get("description", ""),
                display_order=idx,
            ))

        job.status = JobStatus.COMPLETED
        db.commit()
        db.refresh(story)
        
        return str(story.id)
    finally:
        db.close()


def _send_completion_webhook(
    webhook_url: str, job_id: str, story_id: str,
    story_text: str, story_title: str,
    image_urls: list, image_metadata: list,
    video_urls: list, video_metadata: list
) -> None:
    """
    Send webhook notification after story is successfully persisted.
    """
    # Load story from DB to get full relationship data for webhook payload
    db = SessionLocal()
    try:
        story = db.query(Story).filter(Story.id == uuid.UUID(story_id)).first()
        if not story:
            logger.warning(f"Story {story_id} not found for webhook payload")
            return
        
        webhook_payload = {
            "job_id": job_id,
            "status": "completed",
            "story": {
                "id": str(story.id),
                "title": story.title,
                "content": story.content,
                "age_group": story.age_group,
                "images": [
                    {
                        "url": img.image_url,
                        "prompt": img.prompt_used,
                        "description": img.scene_description,
                        "order": img.display_order,
                    }
                    for img in sorted(story.images, key=lambda x: x.display_order)
                ],
                "videos": [
                    {
                        "url": vid.video_url,
                        "prompt": vid.prompt_used,
                        "description": vid.scene_description,
                        "order": vid.display_order,
                    }
                    for vid in sorted(story.videos, key=lambda x: x.display_order)
                ],
            },
        }
        
        send_webhook_sync(webhook_url, webhook_payload)
    finally:
        db.close()
