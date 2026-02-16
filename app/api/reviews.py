"""
Review API endpoints for human-in-the-loop story moderation.

Provides:
- GET  /reviews/pending          — List stories awaiting human review
- GET  /reviews/{job_id}         — Get full review package for a story
- POST /reviews/{job_id}/decide  — Submit approve/reject decision (resumes the graph)
- POST /reviews/{job_id}/regenerate — Regenerate a rejected story
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.api.auth import verify_api_key
from app.models.story import StoryJob, Story, StoryImage, StoryVideo, JobStatus
from app.models.evaluation import StoryEvaluation
from app.models.guardrail import GuardrailResult
from app.models.review import StoryReview
from app.schemas.review import (
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    PendingReviewItem,
    PendingReviewListResponse,
    ReviewDetailResponse,
    EvaluationScoresResponse,
    GuardrailViolationResponse,
    RegenerateResponse,
)
from app.schemas.story import GenerateStoryResponse
from app.tasks.story_tasks import generate_story_task, update_job_status_redis
from app.agents.graph import story_graph
from app.constants import SEVERITY_HARD, SEVERITY_SOFT
from app.utils.url import convert_local_path_to_url
import uuid
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/pending", response_model=PendingReviewListResponse)
async def list_pending_reviews(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all stories awaiting human review."""
    # Query jobs with PENDING_REVIEW status
    result = await db.execute(
        select(
            StoryJob,
            Story.title.label("story_title"),
            Story.id.label("story_id"),
        )
        .outerjoin(Story, Story.job_id == StoryJob.id)
        .where(StoryJob.status == JobStatus.PENDING_REVIEW)
        .order_by(StoryJob.created_at.asc())  # oldest first (FIFO)
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()

    # Get total count
    count_result = await db.execute(
        select(func.count(StoryJob.id))
        .where(StoryJob.status == JobStatus.PENDING_REVIEW)
    )
    total = count_result.scalar() or 0

    reviews = []
    for row in rows:
        job = row[0]
        story_title = row[1]
        story_id = row[2]

        # Get evaluation score
        eval_result = await db.execute(
            select(StoryEvaluation.overall_score)
            .where(StoryEvaluation.job_id == job.id)
        )
        eval_score = eval_result.scalar()

        # Count violations by severity
        hard_count_result = await db.execute(
            select(func.count(GuardrailResult.id))
            .where(
                GuardrailResult.job_id == job.id,
                GuardrailResult.severity == SEVERITY_HARD,
            )
        )
        hard_count = hard_count_result.scalar() or 0

        soft_count_result = await db.execute(
            select(func.count(GuardrailResult.id))
            .where(
                GuardrailResult.job_id == job.id,
                GuardrailResult.severity == SEVERITY_SOFT,
            )
        )
        soft_count = soft_count_result.scalar() or 0

        # Count media
        num_images = 0
        num_videos = 0
        if story_id:
            img_count_result = await db.execute(
                select(func.count(StoryImage.id))
                .where(StoryImage.story_id == story_id)
            )
            num_images = img_count_result.scalar() or 0

            vid_count_result = await db.execute(
                select(func.count(StoryVideo.id))
                .where(StoryVideo.story_id == story_id)
            )
            num_videos = vid_count_result.scalar() or 0

        reviews.append(PendingReviewItem(
            job_id=job.id,
            story_title=story_title,
            age_group=job.age_group,
            prompt=job.prompt,
            overall_eval_score=eval_score,
            guardrail_passed=hard_count == 0,
            num_hard_violations=hard_count,
            num_soft_violations=soft_count,
            created_at=job.created_at,
            num_images=num_images,
            num_videos=num_videos,
        ))

    return PendingReviewListResponse(reviews=reviews, total=total)


@router.get("/{job_id}", response_model=ReviewDetailResponse)
async def get_review_detail(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get full review package: story, images, videos, eval scores, guardrail results."""
    # Fetch job
    job_result = await db.execute(
        select(StoryJob).where(StoryJob.id == job_id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Fetch story with images and videos
    story_result = await db.execute(
        select(Story)
        .options(selectinload(Story.images), selectinload(Story.videos))
        .where(Story.job_id == job_id)
    )
    story = story_result.scalar_one_or_none()

    # Fetch evaluation
    eval_result = await db.execute(
        select(StoryEvaluation).where(StoryEvaluation.job_id == job_id)
    )
    evaluation = eval_result.scalar_one_or_none()

    # Fetch guardrail violations
    violations_result = await db.execute(
        select(GuardrailResult)
        .where(GuardrailResult.job_id == job_id)
        .order_by(GuardrailResult.severity.desc(), GuardrailResult.created_at)
    )
    violations = violations_result.scalars().all()

    hard_count = sum(1 for v in violations if v.severity == SEVERITY_HARD)

    # Build guardrail summary
    summary_parts = []
    if evaluation:
        summary_parts.append(f"📊 Overall Quality Score: {evaluation.overall_score}/10")
        if evaluation.evaluation_summary:
            summary_parts.append(f"   {evaluation.evaluation_summary}")
    if hard_count > 0:
        summary_parts.append(f"\n🚫 {hard_count} HARD violation(s)")
    soft_count = sum(1 for v in violations if v.severity == SEVERITY_SOFT)
    if soft_count > 0:
        summary_parts.append(f"⚠️  {soft_count} SOFT warning(s)")
    if not violations:
        summary_parts.append("✅ All guardrails passed")

    # Build response
    image_urls = []
    video_urls = []
    if story:
        image_urls = [
            convert_local_path_to_url(img.image_url, "image")
            for img in sorted(story.images, key=lambda x: x.display_order)
        ]
        video_urls = [
            convert_local_path_to_url(vid.video_url, "video")
            for vid in sorted(story.videos, key=lambda x: x.display_order)
        ]

    return ReviewDetailResponse(
        job_id=job.id,
        story_id=story.id if story else None,
        story_title=story.title if story else None,
        story_text=story.content if story else None,
        age_group=job.age_group,
        prompt=job.prompt,
        evaluation_scores=EvaluationScoresResponse(
            moral_score=evaluation.moral_score,
            theme_appropriateness=evaluation.theme_appropriateness,
            emotional_positivity=evaluation.emotional_positivity,
            age_appropriateness=evaluation.age_appropriateness,
            educational_value=evaluation.educational_value,
            overall_score=evaluation.overall_score,
            evaluation_summary=evaluation.evaluation_summary,
        ) if evaluation else None,
        guardrail_passed=hard_count == 0,
        guardrail_summary="\n".join(summary_parts) if summary_parts else None,
        violations=[
            GuardrailViolationResponse(
                guardrail_name=v.guardrail_name,
                media_type=v.media_type,
                media_index=v.media_index,
                severity=v.severity,
                confidence=v.confidence,
                detail=v.detail,
            )
            for v in violations
        ],
        image_urls=image_urls,
        video_urls=video_urls,
        created_at=job.created_at,
        parent_job_id=job.parent_job_id,
    )


@router.post("/{job_id}/decide", response_model=ReviewDecisionResponse)
async def submit_review_decision(
    job_id: uuid.UUID,
    decision: ReviewDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a human review decision (approve or reject).
    This resumes the paused LangGraph interrupt.
    """
    # Verify the job exists and is pending review
    job_result = await db.execute(
        select(StoryJob).where(StoryJob.id == job_id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != JobStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is in '{job.status.value}' state, not 'pending_review'",
        )

    # Resume the interrupted graph
    try:
        from langgraph.types import Command

        config = {"configurable": {"thread_id": str(job_id)}}
        resume_value = {
            "decision": decision.decision,
            "comment": decision.comment or "",
            "reviewer_id": decision.reviewer_id or "",
        }

        logger.info(f"Job {job_id}: Resuming graph with decision={decision.decision}")

        # Run the graph resume in a background thread since it may involve
        # async operations (publisher node uploads to S3)
        final_state = await story_graph.ainvoke(
            Command(resume=resume_value),
            config=config,
        )

        # The story_tasks._handle_review_outcome would normally handle DB updates,
        # but since we're resuming from the API (not Celery), handle it here
        review_decision = final_state.get("review_decision", decision.decision)

        if review_decision == "approved":
            # Persist review and update status
            existing_review = await db.execute(
                select(StoryReview).where(StoryReview.job_id == job_id)
            )
            if not existing_review.scalar_one_or_none():
                eval_result = await db.execute(
                    select(StoryEvaluation.overall_score)
                    .where(StoryEvaluation.job_id == job_id)
                )
                eval_score = eval_result.scalar()

                db.add(StoryReview(
                    id=uuid.uuid4(),
                    job_id=job_id,
                    reviewer_id=decision.reviewer_id or "",
                    decision=decision.decision,
                    comment=decision.comment or "",
                    guardrail_passed=True,
                    overall_eval_score=eval_score,
                ))

            job.status = JobStatus.PUBLISHED
            await db.commit()
            update_job_status_redis(str(job_id), "published")

            return ReviewDecisionResponse(
                job_id=job_id,
                decision="approved",
                message="Story approved and published successfully",
            )
        else:
            # Rejected
            existing_review = await db.execute(
                select(StoryReview).where(StoryReview.job_id == job_id)
            )
            if not existing_review.scalar_one_or_none():
                db.add(StoryReview(
                    id=uuid.uuid4(),
                    job_id=job_id,
                    reviewer_id=decision.reviewer_id or "",
                    decision=decision.decision,
                    comment=decision.comment or "",
                    guardrail_passed=True,
                ))

            job.status = JobStatus.REJECTED
            await db.commit()
            update_job_status_redis(str(job_id), "rejected")

            return ReviewDecisionResponse(
                job_id=job_id,
                decision="rejected",
                message="Story rejected. Use the regenerate endpoint to create a new version.",
            )

    except Exception as e:
        logger.error(f"Job {job_id}: Failed to resume graph: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process review decision: {str(e)}",
        )


@router.post("/{job_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_story(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate a rejected story.
    Creates a new job with the same prompt, linked via parent_job_id.
    """
    # Verify the original job exists and was rejected
    job_result = await db.execute(
        select(StoryJob).where(StoryJob.id == job_id)
    )
    original = job_result.scalar_one_or_none()

    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if original.status not in (JobStatus.REJECTED, JobStatus.AUTO_REJECTED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Job is in '{original.status.value}' state. "
                f"Only rejected or auto_rejected jobs can be regenerated."
            ),
        )

    # Create new job linked to original
    new_job = StoryJob(
        id=uuid.uuid4(),
        prompt=original.prompt,
        age_group=original.age_group,
        num_illustrations=original.num_illustrations,
        generate_images=original.generate_images,
        generate_videos=original.generate_videos,
        webhook_url=original.webhook_url,
        parent_job_id=original.id,
        status=JobStatus.PENDING,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)

    # Dispatch to Celery
    task = generate_story_task.delay(str(new_job.id))
    new_job.celery_task_id = task.id
    await db.commit()

    # Cache initial status
    update_job_status_redis(str(new_job.id), "pending")

    logger.info(
        f"Regeneration started: new job {new_job.id} from original {job_id}"
    )

    return RegenerateResponse(
        new_job_id=new_job.id,
        original_job_id=job_id,
        status="pending",
        message=f"Regeneration started. New job {new_job.id} linked to original {job_id}.",
    )
