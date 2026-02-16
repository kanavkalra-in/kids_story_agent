"""
Image Guardrail Node — Vision-based safety check with retry/regeneration.

For each image, this node:
1. Runs vision safety analysis (NSFW, weapons, horror, realistic children)
2. If a hard violation is found, regenerates the image and re-checks
3. Repeats up to ``media_guardrail_max_retries`` times
4. Returns the final URL (good or last-attempt) along with any violations

The retry loop lives INSIDE this node (not as a graph cycle) because:
- image_urls uses operator.add reducer; a graph cycle would append, not replace
- Each image retries independently in parallel — fast images don't wait for slow ones
- Graph topology stays simple with no cycles
"""

import asyncio
import uuid
import logging

import httpx

from app.agents.state import StoryState
from app.agents.nodes.generation.prompter_utils import StoryGenerationError
from app.services.moderation import check_image_safety_async, build_image_violations
from app.services.openai_client import get_openai_client
from app.services.s3 import s3_service
from app.config import settings
from app.constants import HTTP_TIMEOUT, SEVERITY_HARD
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


async def _regenerate_single_image(prompt: str, job_id: str) -> str:
    """Regenerate a single image using DALL-E and store it."""
    client = get_openai_client()

    response = await asyncio.to_thread(
        client.images.generate,
        model=settings.dalle_model,
        prompt=prompt,
        size=settings.dalle_size,
        quality=settings.dalle_quality,
        n=1,
    )

    if not response.data or len(response.data) == 0:
        raise StoryGenerationError("DALL-E API returned no image data during regeneration")

    image_url = response.data[0].url

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http_client:
        img_response = await http_client.get(image_url)
        img_response.raise_for_status()
        image_data = img_response.content

    image_id = str(uuid.uuid4())

    if settings.storage_type == "local":
        final_url = await asyncio.to_thread(
            _save_image_locally, image_data, job_id, image_id
        )
    else:
        final_url = await asyncio.to_thread(
            s3_service.upload_image, image_data, job_id, image_id
        )

    return final_url


async def image_guardrail_with_retry_node(state: StoryState) -> dict:
    """
    Check a single image for safety. If hard violation found, regenerate
    and re-check up to ``media_guardrail_max_retries`` times.

    Invoked via LangGraph ``Send`` with:
    - ``_guardrail_media_url``: URL of the image to check
    - ``_guardrail_media_index``: display-order index
    - ``_guardrail_original_prompt``: the DALL-E prompt (for regeneration)
    """
    job_id = state.get("job_id", "unknown")
    image_url = state.get("_guardrail_media_url", "")
    image_index = state.get("_guardrail_media_index", 0)
    original_prompt = state.get("_guardrail_original_prompt", "")
    age_group = state.get("age_group", "6-8")
    max_retries = settings.media_guardrail_max_retries

    all_violations = []

    for attempt in range(max_retries + 1):
        logger.info(
            f"Job {job_id}: Checking image {image_index} safety (attempt {attempt + 1}/{max_retries + 1})"
        )

        # Run vision safety analysis
        safety_output = await check_image_safety_async(image_url, age_group)
        attempt_violations = build_image_violations(
            safety_output, media_index=image_index, media_type="image"
        )

        hard_violations = [v for v in attempt_violations if v["severity"] == SEVERITY_HARD]

        if not hard_violations:
            logger.info(
                f"Job {job_id}: Image {image_index} passed guardrails "
                f"(attempt {attempt + 1}, {len(attempt_violations)} soft warnings)"
            )
            return {
                "guardrail_violations": attempt_violations,
                "image_urls_final": [{"index": image_index, "url": image_url}],
                "video_urls_final": [],
            }

        # Hard violation — regenerate if retries left
        all_violations.extend(attempt_violations)

        if attempt < max_retries:
            logger.warning(
                f"Job {job_id}: Image {image_index} failed guardrails "
                f"({len(hard_violations)} hard violations), regenerating..."
            )
            try:
                image_url = await _regenerate_single_image(original_prompt, job_id)
                logger.info(f"Job {job_id}: Image {image_index} regenerated → {image_url}")
            except Exception as e:
                logger.error(
                    f"Job {job_id}: Image {image_index} regeneration failed: {e}"
                )
                break  # Can't retry if regeneration itself fails

    # Max retries exhausted — return with all accumulated violations
    logger.error(
        f"Job {job_id}: Image {image_index} failed after {max_retries + 1} attempts "
        f"({len(all_violations)} total violations)"
    )
    return {
        "guardrail_violations": all_violations,
        "image_urls_final": [{"index": image_index, "url": image_url}],
        "video_urls_final": [],
    }
