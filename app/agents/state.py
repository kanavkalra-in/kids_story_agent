from typing import TypedDict, List, Optional
from typing_extensions import Annotated
import operator


class StoryState(TypedDict):
    """State for the story generation workflow"""
    job_id: str
    prompt: str
    age_group: str
    num_illustrations: int
    webhook_url: Optional[str]
    
    # Story generation
    story_text: Optional[str]
    story_title: Optional[str]
    
    # Image generation
    image_prompts: Annotated[List[str], operator.add]  # List of prompts for images
    image_urls: Annotated[List[str], operator.add]  # List of S3/CloudFront URLs
    image_metadata: Annotated[List[dict], operator.add]  # List of metadata dicts
    
    # Error handling
    error: Optional[str]
