from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.db.session import get_db
from app.api.auth import verify_api_key
from app.schemas.story import (
    StoryRequest,
    StoryResponse,
    StoryImageResponse,
    StoryVideoResponse,
    JobStatusResponse,
    GenerateStoryResponse,
    StoryListResponse,
    StoryListItem,
)
from app.models.story import StoryJob, Story, StoryImage, StoryVideo, JobStatus
from app.tasks.story_tasks import generate_story_task, update_job_status_redis
from app.config import settings, limiter
from app.services.redis_client import redis_client
from app.constants import (
    VALID_AGE_GROUPS,
    MAX_PROMPT_LENGTH_CHARS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
)
from app.utils.security import validate_webhook_url_no_ssrf
from app.utils.url import convert_local_path_to_url
from pathlib import Path
import mimetypes
import uuid
import json
import os

router = APIRouter(prefix="/stories", tags=["stories"], dependencies=[Depends(verify_api_key)])




@router.post("/generate", response_model=GenerateStoryResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def generate_story(
    request: Request,
    story_request: StoryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a new story. Returns immediately with a job_id.
    The story will be generated asynchronously via Celery.
    """
    # Input validation and sanitization
    if story_request.age_group not in VALID_AGE_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"age_group must be one of: {', '.join(VALID_AGE_GROUPS)}",
        )
    
    # Validate prompt length (prevent DoS)
    max_prompt_length = settings.max_request_size_mb * 1024 * 1024  # Convert MB to bytes
    if len(story_request.prompt.encode('utf-8')) > max_prompt_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt is too long. Maximum size is {settings.max_request_size_mb}MB",
        )
    
    # Sanitize prompt (limit length)
    sanitized_prompt = story_request.prompt.strip()[:MAX_PROMPT_LENGTH_CHARS]
    if not sanitized_prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt cannot be empty",
        )
    
    # Validate webhook URL if provided — resolve and block private/reserved IPs (SSRF)
    if story_request.webhook_url:
        validate_webhook_url_no_ssrf(str(story_request.webhook_url))
    
    # Create job record with sanitized prompt
    job = StoryJob(
        id=uuid.uuid4(),
        prompt=sanitized_prompt,
        age_group=story_request.age_group,
        num_illustrations=story_request.num_illustrations,
        generate_images=story_request.generate_images,
        generate_videos=story_request.generate_videos,
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
    db: AsyncSession = Depends(get_db),
):
    """Get the status of a story generation job"""
    # Try Redis cache first
    cache_key = f"job_status:{job_id}"
    cached = redis_client.get(cache_key)
    
    # Always fetch job from DB for timestamps and story_id
    # Use a single query with left join to get both job and story
    result = await db.execute(
        select(StoryJob, Story.id.label('story_id'))
        .outerjoin(Story, Story.job_id == StoryJob.id)
        .where(StoryJob.id == job_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    
    job, story_id = row
    
    # Use cached status if available, otherwise use DB status
    if cached:
        cache_data = json.loads(cached)
        status_value = cache_data["status"]
        error_value = cache_data.get("error")
    else:
        status_value = job.status.value
        error_value = job.error_message
    
    return JobStatusResponse(
        job_id=job.id,
        status=status_value,
        error=error_value,
        story_id=story_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("", response_model=StoryListResponse)
async def list_stories(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all completed stories"""
    # Use window function to get total count in the same query as data
    result = await db.execute(
        select(
            Story,
            func.count(StoryImage.id.distinct()).label('num_images'),
            func.count(StoryVideo.id.distinct()).label('num_videos'),
            func.count(Story.id).over().label('total')
        )
        .outerjoin(StoryImage, Story.id == StoryImage.story_id)
        .outerjoin(StoryVideo, Story.id == StoryVideo.story_id)
        .group_by(Story.id)
        .order_by(Story.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()
    
    # Extract total from first row (all rows have the same total due to window function)
    total = rows[0].total if rows else 0
    
    # Build story items
    story_items = []
    for row in rows:
        story, num_images, num_videos, _ = row
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
    db: AsyncSession = Depends(get_db),
):
    """Get a completed story by ID (accepts both story_id and job_id)"""
    # First, try to find story by story_id
    result = await db.execute(
        select(Story)
        .options(selectinload(Story.images), selectinload(Story.videos))
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
                .options(selectinload(Story.images), selectinload(Story.videos))
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
            StoryImageResponse(
                id=img.id,
                image_url=convert_local_path_to_url(img.image_url, "image"),
                prompt_used=img.prompt_used,
                scene_description=img.scene_description,
                display_order=img.display_order,
            )
            for img in sorted(story.images, key=lambda x: x.display_order)
        ],
        videos=[
            StoryVideoResponse(
                id=vid.id,
                video_url=convert_local_path_to_url(vid.video_url, "video"),
                prompt_used=vid.prompt_used,
                scene_description=vid.scene_description,
                display_order=vid.display_order,
            )
            for vid in sorted(story.videos, key=lambda x: x.display_order)
        ],
    )


@router.get("/images/{file_path:path}")
async def serve_image(file_path: str):
    """
    Serve images from local storage.
    Path format: stories/{story_id}/{image_id}.png
    """
    # Security: prevent directory traversal and validate path
    if ".." in file_path or file_path.startswith("/") or "\\" in file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )
    
    # Validate file extension
    if not file_path.lower().endswith(ALLOWED_IMAGE_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only image files are allowed.",
        )
    
    # Construct full path and ensure it's within storage directory
    base_storage_path = Path(settings.local_storage_path)
    if not base_storage_path.is_absolute():
        base_storage_path = Path.cwd() / base_storage_path
    
    image_path = (base_storage_path / file_path).resolve()
    
    # Security: ensure resolved path is within base storage directory
    try:
        image_path.relative_to(base_storage_path.resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path - path traversal detected",
        )
    
    # Check if file exists
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {file_path}",
        )
    
    # Detect content type from extension
    content_type, _ = mimetypes.guess_type(str(image_path))
    return FileResponse(
        path=str(image_path),
        media_type=content_type or "application/octet-stream",
        filename=os.path.basename(file_path),
    )


@router.get("/videos/{file_path:path}")
async def serve_video(file_path: str):
    """
    Serve videos from local storage.
    Path format: stories/{story_id}/{video_id}.mp4
    """
    # Security: prevent directory traversal and validate path
    if ".." in file_path or file_path.startswith("/") or "\\" in file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )
    
    # Validate file extension
    if not file_path.lower().endswith(ALLOWED_VIDEO_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only video files are allowed.",
        )
    
    # Construct full path - videos are stored in configured video storage path
    videos_base = Path(settings.local_video_storage_path)
    if not videos_base.is_absolute():
        videos_base = Path.cwd() / videos_base
    
    video_path = (videos_base / file_path).resolve()
    
    # Security: ensure resolved path is within videos directory
    try:
        video_path.relative_to(videos_base.resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path - path traversal detected",
        )
    
    # Check if file exists
    if not video_path.exists() or not video_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video not found: {file_path}",
        )
    
    # Detect content type from extension
    content_type, _ = mimetypes.guess_type(str(video_path))
    return FileResponse(
        path=str(video_path),
        media_type=content_type or "application/octet-stream",
        filename=os.path.basename(file_path),
    )
