from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime
import uuid


class StoryRequest(BaseModel):
    prompt: str = Field(..., description="The story prompt/idea")
    age_group: str = Field(..., description="Target age group (3-5, 6-8, or 9-12)")
    num_illustrations: int = Field(default=3, ge=1, le=10, description="Number of illustrations")
    webhook_url: Optional[HttpUrl] = Field(None, description="Optional webhook URL for completion notification")
    generate_images: bool = Field(default=True, description="Whether to generate images")
    generate_videos: bool = Field(default=False, description="Whether to generate videos")


class StoryResponse(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    age_group: str
    prompt: str
    created_at: datetime
    images: List["StoryImageResponse"]
    videos: List["StoryVideoResponse"]

    class Config:
        from_attributes = True


class StoryImageResponse(BaseModel):
    id: uuid.UUID
    image_url: str
    prompt_used: str
    scene_description: Optional[str]
    display_order: int

    class Config:
        from_attributes = True


class StoryVideoResponse(BaseModel):
    id: uuid.UUID
    video_url: str
    prompt_used: str
    scene_description: Optional[str]
    display_order: int

    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str  # pending, processing, guardrail_check, pending_review, approved, rejected, auto_rejected, published, completed, failed
    error: Optional[str] = None
    story_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class GenerateStoryResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str


class StoryListItem(BaseModel):
    id: uuid.UUID
    title: str
    age_group: str
    prompt: str
    created_at: datetime
    num_images: int

    class Config:
        from_attributes = True


class StoryListResponse(BaseModel):
    stories: List[StoryListItem]
    total: int


class RejectedStoryItem(BaseModel):
    """Summary of a rejected story."""
    job_id: uuid.UUID
    story_id: Optional[uuid.UUID] = None
    story_title: Optional[str] = None
    story_content: Optional[str] = None
    age_group: str
    prompt: str
    rejection_reason: Optional[str] = None  # "llm_guardrail" / "human" / "timeout"
    comment: Optional[str] = None
    reviewer_id: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    image_urls: List[str] = []

    class Config:
        from_attributes = True


class RejectedStoryListResponse(BaseModel):
    """List of rejected stories."""
    stories: List[RejectedStoryItem]
    total: int


# Update forward references
StoryResponse.model_rebuild()
