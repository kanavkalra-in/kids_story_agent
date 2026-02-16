from sqlalchemy import (
    Column, String, Text, Integer, Boolean, Float,
    ForeignKey, DateTime, Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.db.session import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    GUARDRAIL_CHECK = "guardrail_check"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_REJECTED = "auto_rejected"
    PUBLISHED = "published"
    COMPLETED = "completed"
    FAILED = "failed"


class StoryJob(Base):
    __tablename__ = "story_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt = Column(Text, nullable=False)
    age_group = Column(String(10), nullable=False)  # e.g., "3-5", "6-8", "9-12"
    num_illustrations = Column(Integer, default=3)
    generate_images = Column(Boolean, default=True, nullable=False)
    generate_videos = Column(Boolean, default=False, nullable=False)
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, nullable=False)
    webhook_url = Column(String(500), nullable=True)
    celery_task_id = Column(String(255), nullable=True, unique=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Link to parent job for regeneration traceability
    parent_job_id = Column(UUID(as_uuid=True), ForeignKey("story_jobs.id"), nullable=True)

    # Relationships
    story = relationship("Story", back_populates="job", uselist=False, cascade="all, delete-orphan")
    evaluation = relationship("StoryEvaluation", back_populates="job", uselist=False, cascade="all, delete-orphan")
    guardrail_results = relationship("GuardrailResult", back_populates="job", cascade="all, delete-orphan")
    review = relationship("StoryReview", back_populates="job", uselist=False, cascade="all, delete-orphan")
    parent_job = relationship("StoryJob", remote_side=[id], uselist=False)


class Story(Base):
    __tablename__ = "stories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("story_jobs.id"), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    age_group = Column(String(10), nullable=False)
    prompt = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job = relationship("StoryJob", back_populates="story")
    images = relationship("StoryImage", back_populates="story", cascade="all, delete-orphan", order_by="StoryImage.display_order")
    videos = relationship("StoryVideo", back_populates="story", cascade="all, delete-orphan", order_by="StoryVideo.display_order")


class StoryImage(Base):
    __tablename__ = "story_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id = Column(UUID(as_uuid=True), ForeignKey("stories.id"), nullable=False)
    image_url = Column(String(500), nullable=False)
    prompt_used = Column(Text, nullable=False)
    scene_description = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    story = relationship("Story", back_populates="images")


class StoryVideo(Base):
    __tablename__ = "story_videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id = Column(UUID(as_uuid=True), ForeignKey("stories.id"), nullable=False)
    video_url = Column(String(500), nullable=False)
    prompt_used = Column(Text, nullable=False)
    scene_description = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    story = relationship("Story", back_populates="videos")
