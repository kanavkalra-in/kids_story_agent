from app.services.openai_client import get_openai_client
from app.services.s3 import s3_service
from app.services.storage import save_image_locally
from app.config import settings
from app.agents.state import StoryState
from app.agents.nodes.generation.prompter_utils import StoryGenerationError
from app.constants import HTTP_TIMEOUT
import httpx
import logging
import uuid
import asyncio

logger = logging.getLogger(__name__)


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

    try:
        client = get_openai_client()
        logger.debug(f"Job {job_id}: OpenAI client obtained for image {image_index + 1}")

        # Wrap synchronous OpenAI call in asyncio.to_thread to avoid blocking
        logger.debug(f"Job {job_id}: Calling DALL-E API for image {image_index + 1}")
        logger.debug(f"Job {job_id}: DALL-E params - model={settings.dalle_model}, size={settings.dalle_size}, quality={settings.dalle_quality}")
        
        try:
            response = await asyncio.to_thread(
                client.images.generate,
                model=settings.dalle_model,
                prompt=prompt,
                size=settings.dalle_size,
                quality=settings.dalle_quality,
                n=1,
            )
            logger.debug(f"Job {job_id}: DALL-E API response received for image {image_index + 1}, response type: {type(response)}")
        except asyncio.CancelledError as e:
            error_msg = f"Image {image_index + 1} generation was cancelled"
            logger.error(f"Job {job_id}: {error_msg}")
            raise StoryGenerationError(error_msg) from e
        except Exception as e:
            # Check for content policy violation specifically
            error_str = str(e)
            if "content_policy_violation" in error_str or "content filters" in error_str.lower():
                error_msg = (
                    f"DALL-E content policy violation for image {image_index + 1}. "
                    f"The generated prompt was blocked by OpenAI's content filters. "
                    f"Prompt preview: {prompt[:200]}... "
                    f"This may indicate the image prompter generated content that violates DALL-E's usage policies. "
                    f"Consider reviewing the prompt generation logic or the source story content."
                )
                logger.error(f"Job {job_id}: {error_msg}")
                logger.debug(f"Job {job_id}: Full prompt that was blocked: {prompt}")
                raise StoryGenerationError(error_msg) from e
            else:
                error_msg = f"DALL-E API call failed for image {image_index + 1}: {str(e)}"
                logger.error(f"Job {job_id}: {error_msg}", exc_info=True)
                raise StoryGenerationError(error_msg) from e

        if not response:
            error_msg = f"DALL-E API returned None response for image {image_index + 1}"
            logger.error(f"Job {job_id}: {error_msg}")
            raise StoryGenerationError(error_msg)

        if not hasattr(response, 'data') or not response.data:
            error_msg = f"DALL-E API response missing 'data' attribute for image {image_index + 1}. Response: {response}"
            logger.error(f"Job {job_id}: {error_msg}")
            raise StoryGenerationError(error_msg)

        if len(response.data) == 0:
            error_msg = f"DALL-E API returned empty data array for image {image_index + 1}"
            logger.error(f"Job {job_id}: {error_msg}")
            raise StoryGenerationError(error_msg)

        if not hasattr(response.data[0], 'url') or not response.data[0].url:
            error_msg = f"DALL-E API response missing 'url' for image {image_index + 1}. Data: {response.data[0]}"
            logger.error(f"Job {job_id}: {error_msg}")
            raise StoryGenerationError(error_msg)

        image_url = response.data[0].url
        logger.info(f"Job {job_id}: Image {image_index + 1} generated, downloading from {image_url}")
    except Exception as e:
        error_msg = f"Failed to generate image {image_index + 1}: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}", exc_info=True)
        raise StoryGenerationError(error_msg) from e

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http_client:
            logger.debug(f"Job {job_id}: Downloading image {image_index + 1} from {image_url}")
            img_response = await http_client.get(image_url)
            img_response.raise_for_status()
            image_data = img_response.content

        logger.info(f"Job {job_id}: Image {image_index + 1} downloaded, size: {len(image_data)} bytes")

        story_id = job_id
        image_id = str(uuid.uuid4())

        if settings.storage_type == "local":
            logger.debug(f"Job {job_id}: Saving image {image_index + 1} locally")
            local_path = await asyncio.to_thread(
                save_image_locally, image_data, story_id, image_id
            )
            final_url = local_path
            logger.info(f"Job {job_id}: Image {image_index + 1} saved locally: {local_path}")
        else:
            logger.debug(f"Job {job_id}: Uploading image {image_index + 1} to S3")
            final_url = await asyncio.to_thread(
                s3_service.upload_image, image_data, story_id, image_id
            )
            logger.info(f"Job {job_id}: Image {image_index + 1} uploaded to S3: {final_url}")

        logger.info(f"Job {job_id}: Image {image_index + 1} generation completed successfully, returning URL: {final_url}")
        return {
            "image_urls": [final_url],
            "image_metadata": [{
                "prompt": prompt,
                "description": description,
                "image_index": image_index,
            }],
        }
    except Exception as e:
        error_msg = f"Failed to download/save image {image_index + 1}: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}", exc_info=True)
        raise StoryGenerationError(error_msg) from e
