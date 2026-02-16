"""Individual guardrail check results (one row per violation detected)."""

from sqlalchemy import Column, String, Text, Integer, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.session import Base


class GuardrailResult(Base):
    """Individual guardrail check result (one row per violation detected)."""
    __tablename__ = "guardrail_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("story_jobs.id"), nullable=False)
    guardrail_name = Column(String(100), nullable=False, index=True)
    media_type = Column(String(20), nullable=False)       # story / image / video
    media_index = Column(Integer, nullable=True)
    severity = Column(String(20), nullable=False)          # hard / soft
    confidence = Column(Float, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job = relationship("StoryJob", back_populates="guardrail_results")
