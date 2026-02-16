"""Human (or automated) review decision for a story."""

from sqlalchemy import Column, String, Text, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.session import Base


class StoryReview(Base):
    """Human (or automated) review decision for a story."""
    __tablename__ = "story_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("story_jobs.id"), nullable=False, unique=True)
    reviewer_id = Column(String(255), nullable=True)
    decision = Column(String(20), nullable=False)          # approved / rejected / auto_rejected / timeout_rejected
    comment = Column(Text, nullable=True)
    rejection_reason = Column(String(50), nullable=True)    # "llm_guardrail" / "human" / "timeout"
    guardrail_passed = Column(Boolean, nullable=False, default=True)
    overall_eval_score = Column(Float, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job = relationship("StoryJob", back_populates="review")
