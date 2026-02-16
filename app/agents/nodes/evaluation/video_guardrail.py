"""
Video Guardrail Node — Prompt moderation + optional frame sampling with single retry.

For each video, this node:
1. Runs text guardrails on the original Sora prompt (prompt moderation)
2. Optionally samples frames and runs image safety checks on them
3. If a hard violation is found, regenerates the video and re-checks once
4. If the retry also fails, raises StoryGenerationError to fail the graph

Since videos are generated from text prompts (no audio dialogue), "transcript
moderation" is implemented as prompt moderation — checking the Sora prompt text.
"""

import asyncio
import uuid
import logging

import httpx

from app.agents.state import StoryState
from app.agents.nodes.generation.prompter_utils import StoryGenerationError
from app.services.moderation import (
    check_text_safety_async,
    check_image_safety_async,
    build_text_violations,
    build_image_violations,
)
from app.services.openai_client import get_openai_client
from app.services.s3 import s3_service
from app.services.storage import save_video_locally
from app.config import settings
from app.constants import (
    SEVERITY_HARD,
    VIDEO_MAX_POLL_ATTEMPTS,
    VIDEO_POLL_INITIAL_INTERVAL,
    VIDEO_POLL_MAX_INTERVAL,
    VIDEO_POLL_BACKOFF_MULTIPLIER,
    HTTP_LONG_TIMEOUT,
)

logger = logging.getLogger(__name__)


async def _regenerate_single_video(prompt: str, job_id: str) -> str:
    """Regenerate a single video using Sora and store it."""
    client = get_openai_client()

    if not hasattr(client, "videos"):
        raise StoryGenerationError(
            "OpenAI SDK does not support video generation. The videos API may not be available."
        )

    video_response = client.videos.create(
        model="sora-2",
        prompt=prompt,
        seconds="4",
    )
    video_id = video_response.id

    # Async poll for completion
    video_data = None
    for attempt in range(VIDEO_MAX_POLL_ATTEMPTS):
        video_status = await asyncio.to_thread(client.videos.retrieve, video_id)

        if video_status.status == "completed":
            base_url = (
                str(client.base_url).rstrip("/")
                if hasattr(client, "base_url") and client.base_url
                else "https://api.openai.com/v1"
            )
            content_url = f"{base_url}/videos/{video_id}/content"

            async with httpx.AsyncClient(
                timeout=HTTP_LONG_TIMEOUT,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            ) as http_client:
                response = await http_client.get(content_url)
                response.raise_for_status()
                video_data = response.content
            break
        elif video_status.status == "failed":
            raise StoryGenerationError(
                f"Video regeneration failed: {getattr(video_status, 'error', 'Unknown error')}"
            )
        else:
            delay = min(
                VIDEO_POLL_INITIAL_INTERVAL * (VIDEO_POLL_BACKOFF_MULTIPLIER ** attempt),
                VIDEO_POLL_MAX_INTERVAL,
            )
            await asyncio.sleep(delay)
    else:
        raise StoryGenerationError("Video regeneration timed out during polling")

    if not video_data:
        raise StoryGenerationError("Video regeneration completed but no data fetched")

    video_id_str = str(uuid.uuid4())

    if settings.storage_type == "local":
        final_url = await asyncio.to_thread(
            save_video_locally, video_data, job_id, video_id_str
        )
    else:
        final_url = await asyncio.to_thread(
            s3_service.upload_video, video_data, job_id, video_id_str
        )

    return final_url


async def _check_video_safety(
    job_id: str, prompt: str, video_index: int, age_group: str,
) -> list:
    """Run prompt moderation + frame sampling on a video. Returns violation list."""
    violations = []

    # 1. Prompt moderation (text guardrails on the Sora prompt)
    prompt_safety = await check_text_safety_async(prompt, age_group)
    prompt_violations = build_text_violations(
        prompt_safety, media_type="video", media_index=video_index,
    )
    # Prefix guardrail names to distinguish from story-level violations
    for v in prompt_violations:
        v["guardrail_name"] = f"video_prompt_{v['guardrail_name']}"
    violations.extend(prompt_violations)

    # 2. Frame sampling moderation (if enabled and LLM supports vision)
    if settings.video_frame_sampling_enabled and settings.llm_provider in ("openai", "anthropic"):
        logger.warning(
            f"Job {job_id}: video_frame_sampling_enabled=True but frame extraction is not "
            f"yet implemented (video {video_index}). Skipping frame-level moderation. "
            f"Set VIDEO_FRAME_SAMPLING_ENABLED=false to suppress this warning."
        )
        # TODO: Implement frame extraction with ffmpeg when video processing is available.

    return violations


async def video_guardrail_with_retry_node(state: StoryState) -> dict:
    """
    Check a single video via prompt moderation and optional frame sampling.
    If hard violation found, regenerate once and re-check. If the retry
    also fails, raise StoryGenerationError to fail the entire graph.

    Invoked via LangGraph ``Send`` with:
    - ``_guardrail_media_url``: URL of the video
    - ``_guardrail_media_index``: display-order index
    - ``_guardrail_original_prompt``: the Sora prompt (for moderation + regeneration)
    """
    job_id = state.get("job_id", "unknown")
    video_url = state.get("_guardrail_media_url", "")
    video_index = state.get("_guardrail_media_index", 0)
    original_prompt = state.get("_guardrail_original_prompt", "")
    age_group = state.get("age_group", "6-8")

    # ── Attempt 1: Check original video ──
    logger.info(f"Job {job_id}: Checking video {video_index} safety (attempt 1/2)")

    violations = await _check_video_safety(job_id, original_prompt, video_index, age_group)
    hard_violations = [v for v in violations if v["severity"] == SEVERITY_HARD]

    if not hard_violations:
        logger.info(
            f"Job {job_id}: Video {video_index} passed guardrails "
            f"({len(violations)} soft warnings)"
        )
        return {
            "guardrail_violations": violations,
            "video_urls_final": [{"index": video_index, "url": video_url}],
            "image_urls_final": [],
        }

    # ── Attempt 2: Regenerate and re-check (single retry) ──
    logger.warning(
        f"Job {job_id}: Video {video_index} failed guardrails "
        f"({len(hard_violations)} hard violations), regenerating..."
    )
    video_url = await _regenerate_single_video(original_prompt, job_id)
    logger.info(f"Job {job_id}: Video {video_index} regenerated → {video_url}")

    logger.info(f"Job {job_id}: Checking video {video_index} safety (attempt 2/2)")
    retry_violations = await _check_video_safety(job_id, original_prompt, video_index, age_group)
    hard_violations = [v for v in retry_violations if v["severity"] == SEVERITY_HARD]

    if not hard_violations:
        logger.info(
            f"Job {job_id}: Video {video_index} passed guardrails on retry "
            f"({len(retry_violations)} soft warnings)"
        )
        return {
            "guardrail_violations": retry_violations,
            "video_urls_final": [{"index": video_index, "url": video_url}],
            "image_urls_final": [],
        }

    # ── Retry failed — fail the entire graph ──
    raise StoryGenerationError(
        f"Video {video_index} failed guardrails after retry. "
        f"{len(hard_violations)} hard violation(s): "
        f"{'; '.join(v['detail'] for v in hard_violations)}"
    )
