from app.agents.state import StoryState
from app.agents.nodes.generation.prompter_utils import StoryGenerationError
import logging

logger = logging.getLogger(__name__)


def assembler_node(state: StoryState) -> dict:
    """
    Assemble and validate the final story results.
    
    This node validates results and sorts them by display order, but does NOT
    persist to the database or send webhooks. Those operations are handled
    in story_tasks.py after the graph completes, providing better separation
    of concerns and retry boundaries.
    """
    job_id = state.get("job_id")
    story_text = state.get("story_text")
    story_title = state.get("story_title")
    image_urls = state.get("image_urls", [])
    image_metadata = state.get("image_metadata", [])
    video_urls = state.get("video_urls", [])
    video_metadata = state.get("video_metadata", [])
    error = state.get("error")

    # Check if there was an error from previous nodes
    if error:
        logger.error(f"Job {job_id}: Cannot assemble story due to error: {error}")
        raise StoryGenerationError(error)

    if not job_id or not story_text:
        error_msg = "Missing required data: job_id or story_text"
        logger.error(f"Job {job_id}: {error_msg}")
        raise StoryGenerationError(error_msg)

    generate_images = state.get("generate_images", False)
    generate_videos = state.get("generate_videos", False)
    expected_count = state.get("num_illustrations", 0)

    # Validate image/video counts
    if generate_images and len(image_urls) == 0:
        raise StoryGenerationError("Image generation was enabled but no images were generated.")
    if generate_videos and len(video_urls) == 0:
        raise StoryGenerationError("Video generation was enabled but no videos were generated.")
    if not generate_images and not generate_videos:
        raise StoryGenerationError("Neither image nor video generation was enabled.")

    if generate_images and len(image_urls) != expected_count:
        raise StoryGenerationError(
            f"Expected {expected_count} images but got {len(image_urls)}."
        )
    if generate_videos and len(video_urls) != expected_count:
        raise StoryGenerationError(
            f"Expected {expected_count} videos but got {len(video_urls)}."
        )

    # Parallel Send instances may complete in any order, so URLs and metadata
    # can arrive out of display-order.  Sort both lists together by the index
    # the generator embedded in metadata so the assembler writes the correct
    # display_order to the database.
    if image_urls:
        assert len(image_metadata) == len(image_urls), (
            f"Image URLs and metadata count mismatch: {len(image_urls)} URLs, "
            f"{len(image_metadata)} metadata entries"
        )
        paired = sorted(
            zip(image_urls, image_metadata),
            key=lambda pair: pair[1].get("image_index", 0),
        )
        image_urls = [u for u, _ in paired]
        image_metadata = [m for _, m in paired]

    if video_urls:
        assert len(video_metadata) == len(video_urls), (
            f"Video URLs and metadata count mismatch: {len(video_urls)} URLs, "
            f"{len(video_metadata)} metadata entries"
        )
        paired = sorted(
            zip(video_urls, video_metadata),
            key=lambda pair: pair[1].get("video_index", 0),
        )
        video_urls = [u for u, _ in paired]
        video_metadata = [m for _, m in paired]

    logger.info(
        f"Job {job_id}: Assembled story with "
        f"{len(image_urls)} images and {len(video_urls)} videos"
    )

    # Return validated and sorted results (DB persistence happens in story_tasks.py)
    return {
        "story_text": story_text,
        "story_title": story_title,
        "image_urls": image_urls,
        "image_metadata": image_metadata,
        "video_urls": video_urls,
        "video_metadata": video_metadata,
    }
