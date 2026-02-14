from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime
import uuid


class StoryRequest(BaseModel):
    prompt: str = Field(..., description="The story prompt/idea")
    age_group: str = Field(..., description="Target age group (3-5, 6-8, or 9-12)")
    num_illustrations: int = Field(default=3, ge=1, le=10, description="Number of illustrations")
    webhook_url: Optional[HttpUrl] = Field(None, description="Optional webhook URL for completion notification")


class StoryResponse(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    age_group: str
    prompt: str
    created_at: datetime
    images: List["StoryImageResponse"]

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


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str  # pending, processing, completed, failed
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


# Update forward references
StoryResponse.model_rebuild()
