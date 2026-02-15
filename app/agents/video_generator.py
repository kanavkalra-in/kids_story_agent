from app.services.openai_client import get_openai_client
from app.services.s3 import s3_service
from app.config import settings
from app.agents.state import StoryState
from app.agents.prompter_utils import StoryGenerationError
from app.constants import (
    VIDEO_MAX_POLL_ATTEMPTS,
    VIDEO_POLL_INITIAL_INTERVAL,
    VIDEO_POLL_MAX_INTERVAL,
    VIDEO_POLL_BACKOFF_MULTIPLIER,
    HTTP_LONG_TIMEOUT,
)
import logging
import uuid
import asyncio
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


def _save_video_locally(video_data: bytes, story_id: str, video_id: str) -> str:
    """Save a video to local storage and return the relative file path."""
    base_storage_path = Path(settings.local_video_storage_path)
    if not base_storage_path.is_absolute():
        base_storage_path = Path.cwd() / base_storage_path

    storage_dir = base_storage_path / "stories" / story_id
    storage_dir.mkdir(parents=True, exist_ok=True)

    video_path = storage_dir / f"{video_id}.mp4"
    with open(video_path, "wb") as f:
        f.write(video_data)

    return str(video_path.relative_to(Path.cwd()))


async def video_generator_node(state: StoryState) -> dict:
    """
    Generate a single video using OpenAI Sora and store it (S3 or local).
    Uses async polling to avoid blocking the event loop.

    When invoked via LangGraph ``Send``, the state dict contains three
    extra runtime keys injected by the routing function:

    * ``_current_prompt``  – the Sora prompt for this video
    * ``_current_index``   – display-order index
    * ``_current_description`` – scene description from the prompter
    """
    job_id = state.get("job_id", "unknown")
    prompt: str = state.get("_current_prompt", "")
    video_index: int = state.get("_current_index", 0)
    description: str = state.get("_current_description", "")

    if not state.get("generate_videos", False):
        return {}

    if not prompt:
        raise StoryGenerationError("No prompt provided for video generation")

    logger.info(f"Job {job_id}: Generating video {video_index + 1} with prompt length {len(prompt)}")

    client = get_openai_client()

    if not hasattr(client, "videos"):
        raise StoryGenerationError(
            "OpenAI SDK does not support video generation yet. "
            "The videos API may not be available."
        )

    # OpenAI Sora API supports seconds parameter ('4', '8', or '12')
    video_response = client.videos.create(
        model="sora-2",
        prompt=prompt,
        seconds="4",
    )
    logger.info(f"Job {job_id}: Video generation with 4-second duration")

    video_id = video_response.id
    logger.info(f"Job {job_id}: Video {video_index + 1} started, video_id: {video_id}")

    # Async poll for completion with exponential backoff
    video_data = None
    for attempt in range(VIDEO_MAX_POLL_ATTEMPTS):
        video_status = await asyncio.to_thread(client.videos.retrieve, video_id)

        if video_status.status == "completed":
            logger.info(f"Job {job_id}: Video {video_index + 1} generation completed")

            base_url = (
                str(client.base_url).rstrip("/")
                if hasattr(client, "base_url") and client.base_url
                else "https://api.openai.com/v1"
            )
            content_url = f"{base_url}/videos/{video_id}/content"

            # Use httpx.AsyncClient with auth to avoid exposing API key in headers dict
            # This prevents the key from appearing in error tracebacks
            async with httpx.AsyncClient(
                timeout=HTTP_LONG_TIMEOUT,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"}
            ) as http_client:
                try:
                    response = await http_client.get(content_url)
                    response.raise_for_status()
                    video_data = response.content
                except httpx.HTTPError as e:
                    # Log error without exposing headers (which contain the API key)
                    logger.error(
                        f"Job {job_id}: Failed to fetch video content from {content_url}: "
                        f"{type(e).__name__}: {str(e)}"
                    )
                    raise StoryGenerationError(f"Failed to fetch video content: {str(e)}") from e

            if not video_data:
                raise StoryGenerationError("Video content endpoint returned no data")

            logger.info(
                f"Job {job_id}: Video {video_index + 1} content fetched, "
                f"size: {len(video_data)} bytes"
            )
            break
        elif video_status.status == "failed":
            raise StoryGenerationError(
                f"Video generation failed: {getattr(video_status, 'error', 'Unknown error')}"
            )
        elif video_status.status in ("queued", "in_progress"):
            # Calculate exponential backoff delay
            delay = min(
                VIDEO_POLL_INITIAL_INTERVAL * (VIDEO_POLL_BACKOFF_MULTIPLIER ** attempt),
                VIDEO_POLL_MAX_INTERVAL
            )
            logger.debug(
                f"Job {job_id}: Video {video_index + 1} status: {video_status.status}, "
                f"waiting {delay:.1f}s (attempt {attempt + 1}/{VIDEO_MAX_POLL_ATTEMPTS})"
            )
            await asyncio.sleep(delay)
        else:
            raise StoryGenerationError(f"Unknown video status: {video_status.status}")
    else:
        raise StoryGenerationError(
            f"Video generation timed out after {VIDEO_MAX_POLL_ATTEMPTS} polling attempts"
        )

    if not video_data:
        raise StoryGenerationError("Video generation completed but no video data fetched")

    story_id = str(state.get("story_id", job_id))
    video_id_str = str(uuid.uuid4())

    if settings.storage_type == "local":
        video_url = await asyncio.to_thread(
            _save_video_locally, video_data, story_id, video_id_str
        )
        logger.info(f"Job {job_id}: Video {video_index + 1} saved locally: {video_url}")
    else:
        video_url = await asyncio.to_thread(
            s3_service.upload_video, video_data, story_id, video_id_str
        )
        logger.info(f"Job {job_id}: Video {video_index + 1} uploaded to S3: {video_url}")

    return {
        "video_urls": [video_url],
        "video_metadata": [{
            "prompt": prompt,
            "description": description,
            "video_index": video_index,
        }],
    }
