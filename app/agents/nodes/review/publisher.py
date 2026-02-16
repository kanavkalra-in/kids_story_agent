"""
Publisher Node — Promotes approved story assets to S3 production.

When a human reviewer approves a story, this node uploads the final
media assets from local/staging storage to the S3 production bucket.
"""

import uuid
import asyncio
import logging
from pathlib import Path

from app.agents.state import StoryState
from app.services.s3 import s3_service
from app.config import settings

logger = logging.getLogger(__name__)


async def publisher_node(state: StoryState) -> dict:
    """
    On approval: promote assets from local/staging storage to S3 production.

    If storage is already S3, assets are already in place.
    If storage is local, upload local files to S3.
    """
    job_id = state.get("job_id", "unknown")

    logger.info(f"Job {job_id}: Publishing approved story to production storage")

    if settings.storage_type == "local":
        published_image_urls = []
        for url in state.get("image_urls", []):
            try:
                file_path = Path(url)
                if file_path.exists():
                    image_data = file_path.read_bytes()
                    s3_url = await asyncio.to_thread(
                        s3_service.upload_image, image_data, job_id, str(uuid.uuid4())
                    )
                    published_image_urls.append(s3_url)
                    logger.info(f"Job {job_id}: Published image to S3: {s3_url}")
                else:
                    # If local file doesn't exist, keep the original URL
                    published_image_urls.append(url)
                    logger.warning(f"Job {job_id}: Local image not found: {url}")
            except Exception as e:
                logger.error(f"Job {job_id}: Failed to publish image {url}: {e}")
                published_image_urls.append(url)

        published_video_urls = []
        for url in state.get("video_urls", []):
            try:
                file_path = Path(url)
                if file_path.exists():
                    video_data = file_path.read_bytes()
                    s3_url = await asyncio.to_thread(
                        s3_service.upload_video, video_data, job_id, str(uuid.uuid4())
                    )
                    published_video_urls.append(s3_url)
                    logger.info(f"Job {job_id}: Published video to S3: {s3_url}")
                else:
                    published_video_urls.append(url)
                    logger.warning(f"Job {job_id}: Local video not found: {url}")
            except Exception as e:
                logger.error(f"Job {job_id}: Failed to publish video {url}: {e}")
                published_video_urls.append(url)

        logger.info(
            f"Job {job_id}: Published {len(published_image_urls)} images, "
            f"{len(published_video_urls)} videos to S3"
        )

        return {
            "image_urls": published_image_urls,
            "video_urls": published_video_urls,
        }
    else:
        # Already stored in S3 — nothing to do
        logger.info(f"Job {job_id}: Assets already in S3, no publish action needed")
        return {}
