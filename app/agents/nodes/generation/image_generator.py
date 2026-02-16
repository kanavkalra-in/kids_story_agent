from app.services.openai_client import get_openai_client
from app.services.s3 import s3_service
from app.config import settings
from app.agents.state import StoryState
from app.agents.nodes.generation.prompter_utils import StoryGenerationError
from app.constants import HTTP_TIMEOUT
import httpx
import logging
import uuid
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)


def _save_image_locally(image_data: bytes, story_id: str, image_id: str) -> str:
    """Save an image to local storage and return the relative file path."""
    base_storage_path = Path(settings.local_storage_path)
    if not base_storage_path.is_absolute():
        base_storage_path = Path.cwd() / base_storage_path

    storage_dir = base_storage_path / "stories" / story_id
    storage_dir.mkdir(parents=True, exist_ok=True)

    image_path = storage_dir / f"{image_id}.png"
    with open(image_path, "wb") as f:
        f.write(image_data)

    return str(image_path.relative_to(Path.cwd()))


async def image_generator_node(state: StoryState) -> dict:
    """
    Generate a single image using DALL-E 3 and store it (S3 or local).
    Uses async to avoid blocking the event loop.

    When invoked via LangGraph ``Send``, the state dict contains three
    extra runtime keys injected by the routing function:

    * ``_current_prompt``  – the DALL-E prompt for this image
    * ``_current_index``   – display-order index
    * ``_current_description`` – scene description from the prompter
    """
    job_id = state.get("job_id", "unknown")
    prompt: str = state.get("_current_prompt", "")
    image_index: int = state.get("_current_index", 0)
    description: str = state.get("_current_description", "")

    if not state.get("generate_images", False):
        return {}

    if not prompt:
        raise StoryGenerationError("No prompt provided for image generation")

    logger.info(f"Job {job_id}: Generating image {image_index + 1} with prompt length {len(prompt)}")

    client = get_openai_client()

    # Wrap synchronous OpenAI call in asyncio.to_thread to avoid blocking
    response = await asyncio.to_thread(
        client.images.generate,
        model=settings.dalle_model,
        prompt=prompt,
        size=settings.dalle_size,
        quality=settings.dalle_quality,
        n=1,
    )

    if not response.data or len(response.data) == 0:
        raise StoryGenerationError("DALL-E API returned no image data")

    image_url = response.data[0].url
    logger.info(f"Job {job_id}: Image {image_index + 1} generated, downloading from {image_url}")

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http_client:
        img_response = await http_client.get(image_url)
        img_response.raise_for_status()
        image_data = img_response.content

    logger.info(f"Job {job_id}: Image {image_index + 1} downloaded, size: {len(image_data)} bytes")

    story_id = job_id
    image_id = str(uuid.uuid4())

    if settings.storage_type == "local":
        local_path = await asyncio.to_thread(
            _save_image_locally, image_data, story_id, image_id
        )
        final_url = local_path
        logger.info(f"Job {job_id}: Image {image_index + 1} saved locally: {local_path}")
    else:
        final_url = await asyncio.to_thread(
            s3_service.upload_image, image_data, story_id, image_id
        )
        logger.info(f"Job {job_id}: Image {image_index + 1} uploaded to S3: {final_url}")

    return {
        "image_urls": [final_url],
        "image_metadata": [{
            "prompt": prompt,
            "description": description,
            "image_index": image_index,
        }],
    }
