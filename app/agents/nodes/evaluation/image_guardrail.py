"""
Image Guardrail Node — Vision-based safety check with single retry.

For each image, this node:
1. Runs vision safety analysis (NSFW, weapons, horror, realistic children)
2. If a hard violation is found, regenerates the image and re-checks once
3. If the retry also fails, raises StoryGenerationError to fail the graph

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
from app.services.storage import save_image_locally
from app.config import settings
from app.constants import HTTP_TIMEOUT, SEVERITY_HARD

logger = logging.getLogger(__name__)


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
            save_image_locally, image_data, job_id, image_id
        )
    else:
        final_url = await asyncio.to_thread(
            s3_service.upload_image, image_data, job_id, image_id
        )

    return final_url


async def image_guardrail_with_retry_node(state: StoryState) -> dict:
    """
    Check a single image for safety. If hard violation found, regenerate
    once and re-check. If the retry also fails, raise StoryGenerationError
    to fail the entire graph.

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

    # ── Attempt 1: Check original image ──
    logger.info(f"Job {job_id}: Checking image {image_index} safety (attempt 1/2)")

    safety_output = await check_image_safety_async(image_url, age_group)
    violations = build_image_violations(safety_output, media_index=image_index, media_type="image")
    hard_violations = [v for v in violations if v["severity"] == SEVERITY_HARD]

    if not hard_violations:
        logger.info(
            f"Job {job_id}: Image {image_index} passed guardrails "
            f"({len(violations)} soft warnings)"
        )
        return {
            "guardrail_violations": violations,
            "image_urls_final": [{"index": image_index, "url": image_url}],
            "video_urls_final": [],
        }

    # ── Attempt 2: Regenerate and re-check (single retry) ──
    logger.warning(
        f"Job {job_id}: Image {image_index} failed guardrails "
        f"({len(hard_violations)} hard violations), regenerating..."
    )
    image_url = await _regenerate_single_image(original_prompt, job_id)
    logger.info(f"Job {job_id}: Image {image_index} regenerated → {image_url}")

    logger.info(f"Job {job_id}: Checking image {image_index} safety (attempt 2/2)")
    safety_output = await check_image_safety_async(image_url, age_group)
    retry_violations = build_image_violations(safety_output, media_index=image_index, media_type="image")
    hard_violations = [v for v in retry_violations if v["severity"] == SEVERITY_HARD]

    if not hard_violations:
        logger.info(
            f"Job {job_id}: Image {image_index} passed guardrails on retry "
            f"({len(retry_violations)} soft warnings)"
        )
        return {
            "guardrail_violations": retry_violations,
            "image_urls_final": [{"index": image_index, "url": image_url}],
            "video_urls_final": [],
        }

    # ── Retry failed — fail the entire graph ──
    raise StoryGenerationError(
        f"Image {image_index} failed guardrails after retry. "
        f"{len(hard_violations)} hard violation(s): "
        f"{'; '.join(v['detail'] for v in hard_violations)}"
    )
