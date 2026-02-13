from app.agents.state import StoryState
from app.models.story import Story, StoryImage, StoryJob, JobStatus
from app.db.session import SessionLocal
from typing import Dict
import uuid
import httpx
import logging

logger = logging.getLogger(__name__)


def _do_db_work(job_id: str, story_text: str, story_title: str, 
                image_urls: list, image_metadata: list, 
                webhook_url: str, state: StoryState) -> Dict:
    """
    Perform the actual database work using sync SQLAlchemy.
    This is called from Celery context, so we use sync operations.
    """
    db = SessionLocal()
    try:
        # Get the job
        job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
        
        if not job:
            return {
                "error": f"Job {job_id} not found",
            }
        
        # Create the story
        story = Story(
            id=uuid.uuid4(),
            job_id=job.id,
            title=story_title or "A Wonderful Story",
            content=story_text,
            age_group=state.get("age_group", "6-8"),
            prompt=state.get("prompt", ""),
        )
        db.add(story)
        db.flush()  # Get the story ID
        
        # Create story images
        for idx, (url, metadata) in enumerate(zip(image_urls, image_metadata)):
            story_image = StoryImage(
                id=uuid.uuid4(),
                story_id=story.id,
                image_url=url,
                prompt_used=metadata.get("prompt", ""),
                scene_description=metadata.get("description", ""),
                display_order=idx,
            )
            db.add(story_image)
        
        # Update job status
        job.status = JobStatus.COMPLETED
        db.commit()
        
        # Refresh to get relationships loaded
        db.refresh(story)
        
        # Prepare webhook payload
        webhook_payload = {
            "job_id": str(job.id),
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
            },
        }
        
        # Send webhook if URL provided (using sync httpx client)
        if webhook_url:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    webhook_url,
                    json=webhook_payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                logger.info(f"Webhook sent successfully to {webhook_url}")
        
        return {
            "story_id": str(story.id),
            "status": "completed",
        }
    finally:
        db.close()


def assembler_node(state: StoryState) -> Dict:
    """
    Assemble the final story: save to DB and trigger webhook.
    
    This is a SYNC node that uses sync SQLAlchemy for Celery compatibility.
    LangGraph's ainvoke will handle sync nodes properly.
    """
    job_id = state.get("job_id")
    story_text = state.get("story_text")
    story_title = state.get("story_title")
    image_urls = state.get("image_urls", [])
    image_metadata = state.get("image_metadata", [])
    webhook_url = state.get("webhook_url")
    error = state.get("error")
    
    # Check if there was an error from previous nodes
    if error:
        logger.error(f"Job {job_id}: Cannot assemble story due to error: {error}")
        _update_job_failed(job_id, error)
        return {
            "error": error,
        }
    
    if not job_id or not story_text:
        error_msg = "Missing required data: job_id or story_text"
        logger.error(f"Job {job_id}: {error_msg}")
        _update_job_failed(job_id, error_msg)
        return {
            "error": error_msg,
        }
    
    # Warn if no images were generated, but still create the story
    if len(image_urls) == 0:
        logger.warning(f"Job {job_id}: No images were generated, but proceeding with story creation")
        logger.warning(f"Job {job_id}: image_urls={image_urls}, image_metadata={image_metadata}")
    
    # Deduplicate images before creating database entries
    # This handles cases where state merging with operator.add created duplicates
    logger.debug(f"Job {job_id}: Before deduplication - {len(image_urls)} URLs, {len(image_metadata)} metadata")
    
    # Deduplicate by URL (same URL = same image, should only be stored once)
    seen_urls = set()
    deduplicated_urls = []
    deduplicated_metadata = []
    
    for i, url in enumerate(image_urls):
        if url not in seen_urls:
            seen_urls.add(url)
            deduplicated_urls.append(url)
            # Get corresponding metadata if available
            if i < len(image_metadata):
                deduplicated_metadata.append(image_metadata[i])
            else:
                # Create a minimal metadata entry if missing
                deduplicated_metadata.append({
                    "image_index": len(deduplicated_urls) - 1,
                    "prompt": "",
                    "description": "",
                })
    
    # If we have more metadata than URLs, truncate metadata
    if len(deduplicated_metadata) > len(deduplicated_urls):
        deduplicated_metadata = deduplicated_metadata[:len(deduplicated_urls)]
    
    # Ensure we have matching lengths
    min_len = min(len(deduplicated_urls), len(deduplicated_metadata))
    deduplicated_urls = deduplicated_urls[:min_len]
    deduplicated_metadata = deduplicated_metadata[:min_len]
    
    # Get expected count from state
    expected_count = state.get("num_illustrations", len(deduplicated_urls))
    
    # Truncate to expected count if we have more
    if len(deduplicated_urls) > expected_count:
        logger.warning(f"Job {job_id}: Got {len(deduplicated_urls)} images but expected {expected_count}. Truncating.")
        deduplicated_urls = deduplicated_urls[:expected_count]
        deduplicated_metadata = deduplicated_metadata[:expected_count]
    
    logger.info(f"Job {job_id}: After deduplication - {len(deduplicated_urls)} unique URLs, {len(deduplicated_metadata)} metadata entries")
    
    # Update image_urls and image_metadata to use deduplicated versions
    image_urls = deduplicated_urls
    image_metadata = deduplicated_metadata
    
    # Run the DB work using sync SQLAlchemy
    result = _do_db_work(job_id, story_text, story_title, image_urls, image_metadata, webhook_url, state)
    if len(image_urls) == 0:
        logger.warning(f"Job {job_id}: Story created successfully but with no images")
    else:
        logger.info(f"Job {job_id}: Story created successfully with {len(image_urls)} images")
    return result


def _update_job_failed(job_id: str, error_msg: str):
    """Helper to update job status to failed using sync SQLAlchemy"""
    db = SessionLocal()
    try:
        job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
        if job:
            job.status = JobStatus.FAILED
            job.error_message = error_msg
            db.commit()
    finally:
        db.close()
