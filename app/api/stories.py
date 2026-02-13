from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.api.deps import get_db_session
from app.schemas.story import (
    StoryRequest,
    StoryResponse,
    JobStatusResponse,
    GenerateStoryResponse,
)
from app.models.story import StoryJob, Story, JobStatus
from app.tasks.story_tasks import generate_story_task, update_job_status_redis
from app.config import settings
from app.config import limiter
import uuid
import redis
import json

router = APIRouter(prefix="/stories", tags=["stories"])

# Redis client for status caching
redis_client = redis.from_url(settings.redis_url)


@router.post("/generate", response_model=GenerateStoryResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def generate_story(
    request: Request,
    story_request: StoryRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Generate a new story. Returns immediately with a job_id.
    The story will be generated asynchronously via Celery.
    """
    # Validate age group
    valid_age_groups = ["3-5", "6-8", "9-12"]
    if story_request.age_group not in valid_age_groups:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"age_group must be one of: {', '.join(valid_age_groups)}",
        )
    
    # Create job record
    job = StoryJob(
        id=uuid.uuid4(),
        prompt=story_request.prompt,
        age_group=story_request.age_group,
        num_illustrations=story_request.num_illustrations,
        webhook_url=str(story_request.webhook_url) if story_request.webhook_url else None,
        status=JobStatus.PENDING,
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    # Dispatch Celery task
    task = generate_story_task.delay(str(job.id))
    
    # Update job with Celery task ID
    job.celery_task_id = task.id
    await db.commit()
    
    # Cache initial status in Redis
    update_job_status_redis(str(job.id), "pending")
    
    return GenerateStoryResponse(
        job_id=job.id,
        status="pending",
        message="Story generation started. Use the job_id to check status.",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get the status of a story generation job"""
    # Try Redis cache first
    cache_key = f"job_status:{job_id}"
    cached = redis_client.get(cache_key)
    
    if cached:
        cache_data = json.loads(cached)
        # Still need to get created_at/updated_at from DB
        result = await db.execute(
            select(StoryJob).where(StoryJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if job:
            # Check if story was created
            story_result = await db.execute(
                select(Story).where(Story.job_id == job_id)
            )
            story = story_result.scalar_one_or_none()
            
            return JobStatusResponse(
                job_id=job.id,
                status=cache_data["status"],
                error=cache_data.get("error"),
                story_id=story.id if story else None,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
    
    # Fallback to DB
    result = await db.execute(
        select(StoryJob).where(StoryJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    
    # Check if story was created
    story_result = await db.execute(
        select(Story).where(Story.job_id == job_id)
    )
    story = story_result.scalar_one_or_none()
    
    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        error=job.error_message,
        story_id=story.id if story else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get a completed story by ID (accepts both story_id and job_id)"""
    # First, try to find story by story_id
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.images))
        .where(Story.id == story_id)
    )
    story = result.scalar_one_or_none()
    
    # If not found, check if it's a job_id
    if not story:
        job_result = await db.execute(
            select(StoryJob).where(StoryJob.id == story_id)
        )
        job = job_result.scalar_one_or_none()
        
        if job:
            # Try to find the story associated with this job
            story_result = await db.execute(
                select(Story)
                .options(selectinload(Story.images))
                .where(Story.job_id == story_id)
            )
            story = story_result.scalar_one_or_none()
            
            if not story:
                # Job exists but story hasn't been created yet
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Story not found for job {story_id}. Job status: {job.status.value}. The story may still be processing or may have failed.",
                )
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story {story_id} not found. This ID does not match any story or job.",
        )
    
    return StoryResponse(
        id=story.id,
        title=story.title,
        content=story.content,
        age_group=story.age_group,
        prompt=story.prompt,
        created_at=story.created_at,
        images=[
            {
                "id": img.id,
                "image_url": img.image_url,
                "prompt_used": img.prompt_used,
                "scene_description": img.scene_description,
                "display_order": img.display_order,
            }
            for img in sorted(story.images, key=lambda x: x.display_order)
        ],
    )
