from openai import OpenAI
from app.services.s3 import s3_service
from app.config import settings
from app.agents.state import StoryState
from typing import Dict
import httpx
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def _save_image_locally(image_data: bytes, story_id: str, image_id: str) -> str:
    """
    Save an image to local storage and return the file path.
    
    Args:
        image_data: Binary image data
        story_id: UUID of the story
        image_id: UUID for the image
        
    Returns:
        Relative file path of the saved image
    """
    # Create directory structure: storage/images/stories/{story_id}/
    # Resolve to absolute path to handle relative paths correctly
    base_storage_path = Path(settings.local_storage_path)
    if not base_storage_path.is_absolute():
        base_storage_path = Path.cwd() / base_storage_path
    
    storage_dir = base_storage_path / "stories" / story_id
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    # Save image file
    image_path = storage_dir / f"{image_id}.png"
    with open(image_path, "wb") as f:
        f.write(image_data)
    
    # Return relative path from project root
    return str(image_path.relative_to(Path.cwd()))


def image_generator_node(state: StoryState, prompt: str, image_index: int) -> Dict:
    """
    Generate a single image using DALL-E 3 and store it (S3 or local storage).
    This node is designed to be called in parallel for multiple images.
    Storage location is determined by settings.storage_type flag.
    
    Args:
        state: Current workflow state
        prompt: DALL-E prompt for this image
        image_index: Index of the image (for ordering)
        
    Returns:
        Dict with image_url and metadata
    """
    job_id = state.get("job_id", "unknown")
    
    if not state.get("job_id"):
        error_msg = "No job_id in state"
        logger.error(f"Job {job_id}: {error_msg}")
        return {
            "error": error_msg,
        }
    
    logger.info(f"Job {job_id}: Generating image {image_index + 1} with prompt length {len(prompt)}")
    
    # Initialize OpenAI client
    if not settings.openai_api_key:
        error_msg = "OpenAI API key not configured"
        logger.error(f"Job {job_id}: {error_msg}")
        return {
            "error": error_msg,
        }
    
    client = OpenAI(api_key=settings.openai_api_key)
    
    # Generate image with DALL-E 3
    logger.debug(f"Job {job_id}: Calling DALL-E 3 API for image {image_index + 1}")
    response = client.images.generate(
        model=settings.dalle_model,
        prompt=prompt,
        size=settings.dalle_size,
        quality=settings.dalle_quality,
        n=1,
    )
    
    if not response.data or len(response.data) == 0:
        error_msg = "DALL-E API returned no image data"
        logger.error(f"Job {job_id}: {error_msg}")
        return {
            "error": error_msg,
        }
    
    image_url = response.data[0].url
    logger.info(f"Job {job_id}: Image {image_index + 1} generated, downloading from {image_url}")
    
    # Download the image
    with httpx.Client(timeout=30.0) as http_client:
        img_response = http_client.get(image_url)
        img_response.raise_for_status()
        image_data = img_response.content
    
    logger.info(f"Job {job_id}: Image {image_index + 1} downloaded, size: {len(image_data)} bytes")
    
    story_id = job_id  # Use job_id as story_id for now (will be actual story_id after creation)
    image_id = str(uuid.uuid4())
    
    # Store image based on storage type flag
    if settings.storage_type == "local":
        # Save to local storage
        logger.info(f"Job {job_id}: Saving image {image_index + 1} to local storage")
        local_path = _save_image_locally(
            image_data=image_data,
            story_id=story_id,
            image_id=image_id,
        )
        image_url = local_path
        logger.info(f"Job {job_id}: Image {image_index + 1} saved to local storage: {local_path}")
    else:
        # Upload to S3
        logger.info(f"Job {job_id}: Uploading image {image_index + 1} to S3")
        image_url = s3_service.upload_image(
            image_data=image_data,
            story_id=story_id,
            image_id=image_id,
        )
        logger.info(f"Job {job_id}: Image {image_index + 1} uploaded to S3: {image_url}")
    
    return {
        "image_urls": [image_url],
        "image_metadata": [{
            "prompt": prompt,
            "image_index": image_index,
            "s3_url": image_url if settings.storage_type == "s3" else None,
            "local_path": image_url if settings.storage_type == "local" else None,
        }],
    }


def create_image_generator_nodes(state: StoryState) -> list:
    """
    Create a list of image generator node calls for parallel execution.
    This will be used with LangGraph's Send API.
    """
    image_prompts = state.get("image_prompts", [])
    nodes = []
    
    for idx, prompt in enumerate(image_prompts):
        nodes.append({
            "node": image_generator_node,
            "args": {
                "prompt": prompt,
                "image_index": idx,
            },
        })
    
    return nodes
