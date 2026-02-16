"""Quality evaluation scores for a generated story."""

from sqlalchemy import Column, Text, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.session import Base


class StoryEvaluation(Base):
    """Quality evaluation scores for a generated story."""
    __tablename__ = "story_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("story_jobs.id"), nullable=False, unique=True)
    moral_score = Column(Float, nullable=False)
    theme_appropriateness = Column(Float, nullable=False)
    emotional_positivity = Column(Float, nullable=False)
    age_appropriateness = Column(Float, nullable=False)
    educational_value = Column(Float, nullable=False)
    overall_score = Column(Float, nullable=False)
    evaluation_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job = relationship("StoryJob", back_populates="evaluation")
