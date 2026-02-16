from langgraph.errors import GraphInterrupt

from app.celery_app import celery_app
from app.agents.graph import run_story_generation
from app.agents.state import StoryState
from app.models.story import Story, StoryImage, StoryVideo, StoryJob, JobStatus
from app.models.evaluation import StoryEvaluation
from app.models.guardrail import GuardrailResult
from app.models.review import StoryReview
from app.db.session import get_sync_db
from app.services.redis_client import get_redis_client
from app.services.webhook import send_webhook_sync
from app.agents.nodes.generation.prompter_utils import StoryGenerationError
from app.constants import (
    JOB_STATUS_CACHE_TTL,
    DEFAULT_STORY_TITLE,
    REVIEW_APPROVED,
    REVIEW_AUTO_REJECTED,
    REVIEW_REJECTED,
)
from typing import Any
import uuid
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# ── Status mapping: string status → JobStatus enum ──
_STATUS_MAP = {
    "pending": JobStatus.PENDING,
    "processing": JobStatus.PROCESSING,
    "pending_review": JobStatus.PENDING_REVIEW,
    "published": JobStatus.PUBLISHED,
    "rejected": JobStatus.REJECTED,
    "auto_rejected": JobStatus.AUTO_REJECTED,
    "failed": JobStatus.FAILED,
}


def update_job_status(job_id: str, status: str, error: str = None):
    """Update job status in both Redis (fast polling) and DB (durable) in one call."""
    # Redis update
    cache_key = f"job_status:{job_id}"
    cache_data = {"status": status, "error": error}
    get_redis_client().setex(cache_key, JOB_STATUS_CACHE_TTL, json.dumps(cache_data))

    # DB update
    db_status = _STATUS_MAP.get(status)
    if db_status is None:
        logger.warning(f"Unknown status '{status}' — skipping DB update for job {job_id}")
        return
    with get_sync_db() as db:
        job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
        if job:
            job.status = db_status
            if error:
                job.error_message = error
            db.commit()


# Keep backward-compatible alias used by reviews API and review_timeout_task
def update_job_status_redis(job_id: str, status: str, error: str = None):
    """Update job status in Redis cache only (for use outside Celery tasks)."""
    cache_key = f"job_status:{job_id}"
    cache_data = {"status": status, "error": error}
    get_redis_client().setex(cache_key, JOB_STATUS_CACHE_TTL, json.dumps(cache_data))


@celery_app.task(bind=True, name="generate_story_task")
def generate_story_task(self, job_id: str) -> dict[str, Any]:
    """
    Celery task to generate a story using LangGraph workflow.

    The graph now includes evaluation, guardrails, and human-in-the-loop.
    When the graph hits ``interrupt()`` at ``human_review_gate``, this task
    completes with status "pending_review". The graph is resumed later
    via the review API endpoint.

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
    """
    # Update status to processing
    update_job_status(job_id, "processing")

    # Load job data from database
    with get_sync_db() as db:
        job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        prompt = job.prompt
        age_group = job.age_group
        num_illustrations = job.num_illustrations
        generate_images = job.generate_images
        generate_videos = job.generate_videos
        webhook_url = job.webhook_url

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
        # Evaluation & guardrail fields
        "evaluation_scores": None,
        "guardrail_violations": [],
        "guardrail_passed": None,
        "guardrail_summary": None,
        "image_urls_final": [],
        "video_urls_final": [],
        # Review fields
        "review_decision": None,
        "review_comment": None,
        "reviewer_id": None,
    }

    # Run the LangGraph workflow
    logger.info(f"Starting story generation for job {job_id}")
    try:
        final_state = await run_story_generation(initial_state, thread_id=job_id)
    except StoryGenerationError as e:
        error_msg = str(e)
        logger.error(f"Story generation failed for job {job_id}: {error_msg}")
        update_job_status(job_id, "failed", error_msg)
        return {"job_id": job_id, "status": "failed", "error": error_msg}
    except GraphInterrupt:
        # LangGraph raises GraphInterrupt when interrupt() is called
        logger.info(f"Job {job_id}: Graph interrupted for human review")
        # Persist pre-review data - if this fails, raise the error (no silent failures)
        _persist_pre_review_data(job_id, initial_state)
        update_job_status(job_id, "pending_review")
        return {"job_id": job_id, "status": "pending_review"}
    except Exception as e:
        # Catch any other exceptions (including Pydantic serialization errors)
        error_msg = f"Unexpected error during story generation: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}", exc_info=True)
        update_job_status(job_id, "failed", error_msg)
        return {"job_id": job_id, "status": "failed", "error": error_msg}

    # Check if the graph was interrupted (for human review)
    # This happens when interrupt() is called — the graph returns partial state
    review_decision = final_state.get("review_decision")

    if review_decision is None:
        # Graph was interrupted — waiting for human review
        logger.info(f"Job {job_id}: Awaiting human review")
        # Persist pre-review data - if this fails, raise the error (no silent failures)
        _persist_pre_review_data(job_id, final_state)
        update_job_status(job_id, "pending_review")
        return {"job_id": job_id, "status": "pending_review"}

    # Process the review decision
    return _handle_review_outcome(job_id, final_state, webhook_url)


def _persist_pre_review_data(job_id: str, state: dict):
    """
    Persist story, evaluation, and guardrail data to DB before human review.
    This ensures the reviewer can see the data even if the Celery worker restarts.
    
    Raises:
        Exception: If persistence fails, the exception is re-raised to ensure
                   the error is not silently ignored.
    """
    try:
        with get_sync_db() as db:
            job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
            if not job:
                error_msg = f"Job {job_id} not found for pre-review persistence"
                logger.error(error_msg)
                raise ValueError(error_msg)

            _ensure_story_persisted(db, job, state)
            _ensure_evaluation_persisted(db, job, state)
            _ensure_guardrails_persisted(db, job, state)

            db.commit()
            logger.info(f"Job {job_id}: Pre-review data persisted to DB")

    except Exception as e:
        error_msg = f"Job {job_id}: Failed to persist pre-review data: {e}"
        logger.error(error_msg, exc_info=True)
        raise  # Re-raise to ensure error is not silently ignored


def _ensure_story_persisted(db, job, state: dict):
    """Persist story + media if not already saved. Reusable across persist paths."""
    existing = db.query(Story).filter(Story.job_id == job.id).first()
    if existing or not state.get("story_text"):
        return existing

    story = Story(
        id=uuid.uuid4(),
        job_id=job.id,
        title=state.get("story_title") or DEFAULT_STORY_TITLE,
        content=state.get("story_text", ""),
        age_group=state.get("age_group", "6-8"),
        prompt=state.get("prompt", ""),
    )
    db.add(story)
    db.flush()

    image_metadata = state.get("image_metadata", [])
    for idx, url in enumerate(state.get("image_urls", [])):
        metadata = image_metadata[idx] if idx < len(image_metadata) else {}
        db.add(StoryImage(
            id=uuid.uuid4(),
            story_id=story.id,
            image_url=url,
            prompt_used=metadata.get("prompt", ""),
            scene_description=metadata.get("description", ""),
            display_order=idx,
        ))

    video_metadata = state.get("video_metadata", [])
    for idx, url in enumerate(state.get("video_urls", [])):
        metadata = video_metadata[idx] if idx < len(video_metadata) else {}
        db.add(StoryVideo(
            id=uuid.uuid4(),
            story_id=story.id,
            video_url=url,
            prompt_used=metadata.get("prompt", ""),
            scene_description=metadata.get("description", ""),
            display_order=idx,
        ))

    return story


def _ensure_evaluation_persisted(db, job, state: dict):
    """Persist evaluation scores if not already saved."""
    eval_scores = state.get("evaluation_scores")
    if not eval_scores:
        return
    existing = db.query(StoryEvaluation).filter(
        StoryEvaluation.job_id == job.id
    ).first()
    if existing:
        return
    db.add(StoryEvaluation(
        id=uuid.uuid4(),
        job_id=job.id,
        moral_score=eval_scores.get("moral_score", 0),
        theme_appropriateness=eval_scores.get("theme_appropriateness", 0),
        emotional_positivity=eval_scores.get("emotional_positivity", 0),
        age_appropriateness=eval_scores.get("age_appropriateness", 0),
        educational_value=eval_scores.get("educational_value", 0),
        overall_score=eval_scores.get("overall_score", 0),
        evaluation_summary=eval_scores.get("evaluation_summary", ""),
    ))


def _ensure_guardrails_persisted(db, job, state: dict):
    """Persist guardrail violations if not already saved."""
    violations = state.get("guardrail_violations", [])
    if not violations:
        return
    existing_count = db.query(GuardrailResult).filter(
        GuardrailResult.job_id == job.id
    ).count()
    if existing_count > 0:
        return
    for v in violations:
        db.add(GuardrailResult(
            id=uuid.uuid4(),
            job_id=job.id,
            guardrail_name=v.get("guardrail_name", "unknown"),
            media_type=v.get("media_type", "unknown"),
            media_index=v.get("media_index"),
            severity=v.get("severity", "soft"),
            confidence=v.get("confidence", 0),
            detail=v.get("detail", ""),
        ))


def _handle_review_outcome(
    job_id: str, final_state: dict, webhook_url: str = None
) -> dict[str, Any]:
    """Handle the final outcome after review (approved, rejected, or auto-rejected)."""
    review_decision = final_state.get("review_decision", "rejected")

    if review_decision == REVIEW_APPROVED:
        # Persist final data and mark as published
        try:
            story_id = _persist_story_to_db(job_id, final_state)

            _persist_review_to_db(job_id, final_state)

            if webhook_url:
                _send_completion_webhook(webhook_url, job_id, story_id)

            update_job_status(job_id, "published")
            logger.info(f"Job {job_id}: Story approved and published")
            return {"job_id": job_id, "status": "published", "story_id": story_id}

        except Exception as e:
            error_msg = f"Failed to publish story: {str(e)}"
            logger.error(f"Job {job_id}: {error_msg}")
            update_job_status(job_id, "failed", error_msg)
            return {"job_id": job_id, "status": "failed", "error": error_msg}

    elif review_decision == REVIEW_AUTO_REJECTED:
        _persist_pre_review_data(job_id, final_state)
        _persist_review_to_db(job_id, final_state)
        update_job_status(job_id, "auto_rejected")
        logger.info(f"Job {job_id}: Auto-rejected by guardrails")
        return {"job_id": job_id, "status": "auto_rejected"}

    else:
        # Human rejected
        _persist_review_to_db(job_id, final_state)
        update_job_status(job_id, "rejected")
        logger.info(f"Job {job_id}: Rejected by human reviewer")
        return {"job_id": job_id, "status": "rejected"}


def _persist_review_to_db(job_id: str, state: dict):
    """
    Persist review decision to the database.
    
    Raises:
        Exception: If persistence fails, the exception is re-raised to ensure
                   the error is not silently ignored.
    """
    try:
        with get_sync_db() as db:
            existing = db.query(StoryReview).filter(
                StoryReview.job_id == uuid.UUID(job_id)
            ).first()
            if not existing:
                eval_scores = state.get("evaluation_scores") or {}
                db.add(StoryReview(
                    id=uuid.uuid4(),
                    job_id=uuid.UUID(job_id),
                    reviewer_id=state.get("reviewer_id", ""),
                    decision=state.get("review_decision", "rejected"),
                    comment=state.get("review_comment", ""),
                    guardrail_passed=state.get("guardrail_passed", False),
                    overall_eval_score=eval_scores.get("overall_score"),
                ))
                db.commit()
    except Exception as e:
        error_msg = f"Job {job_id}: Failed to persist review: {e}"
        logger.error(error_msg, exc_info=True)
        raise  # Re-raise to ensure error is not silently ignored


def _persist_story_to_db(job_id: str, state: dict) -> str:
    """
    Persist story to database using sync SQLAlchemy.
    Called from Celery context, so we use sync operations.

    If the story was already created during pre-review persistence,
    updates the media URLs (they may have changed after S3 publish).

    Returns:
        story_id as string
    """
    image_urls = state.get("image_urls", [])
    image_metadata = state.get("image_metadata", [])
    video_urls = state.get("video_urls", [])
    video_metadata = state.get("video_metadata", [])

    with get_sync_db() as db:
        job = db.query(StoryJob).filter(StoryJob.id == uuid.UUID(job_id)).first()
        if not job:
            raise StoryGenerationError(f"Job {job_id} not found")

        # Check if story already exists (from pre-review persistence)
        existing_story = db.query(Story).filter(Story.job_id == job.id).first()
        if existing_story:
            # Update existing media URLs (may have changed after publish to S3)
            _update_media_urls(db, existing_story, image_urls, image_metadata, video_urls, video_metadata)
            db.commit()
            return str(existing_story.id)

        # Create new story (and media) via shared helper
        story = _ensure_story_persisted(db, job, state)
        if story:
            job.status = JobStatus.PUBLISHED
            db.commit()
            db.refresh(story)
            return str(story.id)

        raise StoryGenerationError(f"Job {job_id}: No story text available to persist")


def _update_media_urls(db, story, image_urls, image_metadata, video_urls, video_metadata):
    """Update existing media URLs on a story (e.g. after S3 publish)."""
    for idx, (url, metadata) in enumerate(zip(image_urls, image_metadata)):
        existing_image = db.query(StoryImage).filter(
            StoryImage.story_id == story.id,
            StoryImage.display_order == idx,
        ).first()
        if existing_image:
            existing_image.image_url = url
        else:
            db.add(StoryImage(
                id=uuid.uuid4(),
                story_id=story.id,
                image_url=url,
                prompt_used=metadata.get("prompt", ""),
                scene_description=metadata.get("description", ""),
                display_order=idx,
            ))

    for idx, (url, metadata) in enumerate(zip(video_urls, video_metadata)):
        existing_video = db.query(StoryVideo).filter(
            StoryVideo.story_id == story.id,
            StoryVideo.display_order == idx,
        ).first()
        if existing_video:
            existing_video.video_url = url
        else:
            db.add(StoryVideo(
                id=uuid.uuid4(),
                story_id=story.id,
                video_url=url,
                prompt_used=metadata.get("prompt", ""),
                scene_description=metadata.get("description", ""),
                display_order=idx,
            ))


def _send_completion_webhook(webhook_url: str, job_id: str, story_id: str) -> None:
    """Send webhook notification after story is approved and published."""
    with get_sync_db() as db:
        story = db.query(Story).filter(Story.id == uuid.UUID(story_id)).first()
        if not story:
            logger.warning(f"Story {story_id} not found for webhook payload")
            return

        webhook_payload = {
            "job_id": job_id,
            "status": "published",
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
