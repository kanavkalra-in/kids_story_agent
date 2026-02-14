from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.api.deps import get_db_session
from app.schemas.story import (
    StoryRequest,
    StoryResponse,
    JobStatusResponse,
    GenerateStoryResponse,
    StoryListResponse,
    StoryListItem,
)
from app.models.story import StoryJob, Story, StoryImage, JobStatus
from app.tasks.story_tasks import generate_story_task, update_job_status_redis
from app.config import settings
from app.config import limiter
from pathlib import Path
import uuid
import redis
import json
import os

router = APIRouter(prefix="/stories", tags=["stories"])

# Redis client for status caching
redis_client = redis.from_url(settings.redis_url)


def _convert_local_path_to_url(image_url: str, request: Request = None) -> str:
    """
    Convert a local file path to an API URL if it's a local storage path.
    If it's already a URL (http/https), return it as-is.
    """
    # If it's already a URL, return as-is
    if image_url.startswith(("http://", "https://")):
        return image_url
    
    # If it's a local path, convert to API endpoint
    if image_url.startswith("storage/"):
        # Extract the path after storage/images/
        # e.g., "storage/images/stories/{story_id}/{image_id}.png"
        # becomes "/api/v1/stories/images/stories/{story_id}/{image_id}.png"
        if image_url.startswith("storage/images/"):
            relative_path = image_url.replace("storage/images/", "")
            # Use relative path - client will resolve it relative to API base URL
            return f"/api/v1/stories/images/{relative_path}"
        # Handle case where path might be storage/images/stories/... directly
        elif "stories/" in image_url:
            # Extract everything after storage/images/ or just stories/
            if "storage/images/stories/" in image_url:
                relative_path = image_url.split("storage/images/stories/", 1)[1]
                return f"/api/v1/stories/images/stories/{relative_path}"
    
    # If it contains stories/ but doesn't start with storage/, it might be a partial path
    # Try to construct the API URL
    if "stories/" in image_url and not image_url.startswith("/"):
        # Assume it's a path like "stories/{story_id}/{image_id}.png"
        return f"/api/v1/stories/images/{image_url}"
    
    return image_url


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


@router.get("", response_model=StoryListResponse)
async def list_stories(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
):
    """List all completed stories"""
    # Get total count
    count_result = await db.execute(select(func.count(Story.id)))
    total = count_result.scalar()
    
    # Get stories with pagination and image counts
    result = await db.execute(
        select(
            Story,
            func.count(StoryImage.id).label('num_images')
        )
        .outerjoin(StoryImage, Story.id == StoryImage.story_id)
        .group_by(Story.id)
        .order_by(Story.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()
    
    # Build story items
    story_items = []
    for row in rows:
        story, num_images = row
        story_items.append(StoryListItem(
            id=story.id,
            title=story.title,
            age_group=story.age_group,
            prompt=story.prompt,
            created_at=story.created_at,
            num_images=num_images or 0,
        ))
    
    return StoryListResponse(
        stories=story_items,
        total=total,
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
                "image_url": _convert_local_path_to_url(img.image_url),
                "prompt_used": img.prompt_used,
                "scene_description": img.scene_description,
                "display_order": img.display_order,
            }
            for img in sorted(story.images, key=lambda x: x.display_order)
        ],
    )


@router.get("/images/{file_path:path}")
async def serve_image(file_path: str):
    """
    Serve images from local storage.
    Path format: stories/{story_id}/{image_id}.png
    """
    # Security: prevent directory traversal
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )
    
    # Construct full path
    base_storage_path = Path(settings.local_storage_path)
    if not base_storage_path.is_absolute():
        base_storage_path = Path.cwd() / base_storage_path
    
    image_path = base_storage_path / file_path
    
    # Check if file exists
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {file_path}",
        )
    
    # Return file with appropriate content type
    return FileResponse(
        path=str(image_path),
        media_type="image/png",
        filename=os.path.basename(file_path),
    )
