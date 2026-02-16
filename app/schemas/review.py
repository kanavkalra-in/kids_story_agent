"""
Pydantic schemas for human review endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


# ── Request Schemas ──


class ReviewDecisionRequest(BaseModel):
    """Request body for submitting a review decision."""
    decision: str = Field(
        ...,
        description="Review decision: 'approved' or 'rejected'",
        pattern="^(approved|rejected)$",
    )
    comment: Optional[str] = Field(None, description="Reviewer's optional comment")
    reviewer_id: Optional[str] = Field(None, description="ID of the reviewer")


# ── Response Schemas ──


class EvaluationScoresResponse(BaseModel):
    """Quality evaluation scores for a story."""
    moral_score: float
    theme_appropriateness: float
    emotional_positivity: float
    age_appropriateness: float
    educational_value: float
    overall_score: float
    evaluation_summary: Optional[str] = None


class GuardrailViolationResponse(BaseModel):
    """A single guardrail violation."""
    guardrail_name: str
    media_type: str
    media_index: Optional[int] = None
    severity: str
    confidence: float
    detail: Optional[str] = None


class PendingReviewItem(BaseModel):
    """Summary of a story pending review."""
    job_id: uuid.UUID
    story_title: Optional[str] = None
    age_group: str
    prompt: str
    overall_eval_score: Optional[float] = None
    guardrail_passed: bool
    num_hard_violations: int
    num_soft_violations: int
    created_at: datetime
    num_images: int = 0
    num_videos: int = 0


class PendingReviewListResponse(BaseModel):
    """List of stories pending human review."""
    reviews: List[PendingReviewItem]
    total: int


class ReviewDetailResponse(BaseModel):
    """Full review package for a single story."""
    job_id: uuid.UUID
    story_id: Optional[uuid.UUID] = None
    story_title: Optional[str] = None
    story_text: Optional[str] = None
    age_group: str
    prompt: str
    evaluation_scores: Optional[EvaluationScoresResponse] = None
    guardrail_passed: bool
    guardrail_summary: Optional[str] = None
    violations: List[GuardrailViolationResponse] = []
    image_urls: List[str] = []
    video_urls: List[str] = []
    created_at: datetime
    parent_job_id: Optional[uuid.UUID] = None


class ReviewDecisionResponse(BaseModel):
    """Response after submitting a review decision."""
    job_id: uuid.UUID
    decision: str
    message: str


class RegenerateResponse(BaseModel):
    """Response after requesting story regeneration."""
    new_job_id: uuid.UUID
    original_job_id: uuid.UUID
    status: str
    message: str
