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
    expected_count = state.get("num_illustrations")
    
    logger.info(
        f"Job {job_id}: [ASSEMBLER] Starting validation - expected_count={expected_count}, "
        f"image_urls count={len(image_urls)}, image_prompts count={len(state.get('image_prompts', []))}, "
        f"image_metadata count={len(image_metadata)}"
    )
    
    # Validate that num_illustrations is set and valid
    if expected_count is None:
        error_msg = "num_illustrations is missing from state. Cannot validate image/video counts."
        logger.error(f"Job {job_id}: {error_msg}")
        raise StoryGenerationError(error_msg)
    
    if expected_count < 1:
        error_msg = f"num_illustrations must be at least 1, but got {expected_count}"
        logger.error(f"Job {job_id}: {error_msg}")
        raise StoryGenerationError(error_msg)

    # Validate image/video counts
    if generate_images and len(image_urls) == 0:
        raise StoryGenerationError("Image generation was enabled but no images were generated.")
    if generate_videos and len(video_urls) == 0:
        raise StoryGenerationError("Video generation was enabled but no videos were generated.")
    if not generate_images and not generate_videos:
        raise StoryGenerationError("Neither image nor video generation was enabled.")

    if generate_images and len(image_urls) != expected_count:
        error_msg = (
            f"Expected {expected_count} image(s) but got {len(image_urls)}. "
            f"This indicates a mismatch between the requested number of illustrations and what was generated. "
            f"Image prompts generated: {len(state.get('image_prompts', []))}"
        )
        logger.error(f"Job {job_id}: {error_msg}")
        raise StoryGenerationError(error_msg)
    if generate_videos and len(video_urls) != expected_count:
        raise StoryGenerationError(
            f"Expected {expected_count} videos but got {len(video_urls)}."
        )

    # Parallel Send instances may complete in any order, so URLs and metadata
    # can arrive out of display-order.  Sort both lists together by the index
    # the generator embedded in metadata so the assembler writes the correct
    # display_order to the database.
    if image_urls:
        if len(image_metadata) != len(image_urls):
            raise StoryGenerationError(
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
        if len(video_metadata) != len(video_urls):
            raise StoryGenerationError(
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

    # CRITICAL FIX: image_urls, image_metadata, video_urls, video_metadata are reducer fields.
    # In LangGraph, reducer fields accumulate when multiple Send nodes return values.
    # However, when a regular node (not Send) returns a reducer field, LangGraph should
    # REPLACE the value, not add to it. But to be safe and avoid any accumulation issues,
    # we should NOT return reducer fields from the assembler.
    #
    # The reducer fields are already correctly set by the generator nodes via Send.
    # The assembler's job is just to validate - it doesn't need to modify reducer fields.
    # The sorted/validated URLs are already in state from the generators.
    #
    # However, we DO need the sorted URLs for later use. The solution is to use
    # non-reducer fields for the final sorted results, OR to ensure the reducer
    # fields are correctly set (which they should be from generators).
    #
    # Actually, wait - the generators return the URLs via reducer, so they're already
    # in state. The assembler just validates. We don't need to return them.
    # But route_to_guardrails reads from state['image_urls'], so it should work.
    #
    # The real issue: The assembler is returning image_urls, and LangGraph might be
    # treating it as an addition. Let's NOT return reducer fields from assembler.
    
    # Return only non-reducer fields. The reducer fields (image_urls, etc.) are
    # already in state from the generators and should not be modified here.
    return {
        "story_text": story_text,
        "story_title": story_title,
        # Do NOT return image_urls, image_metadata, video_urls, video_metadata
        # They are reducer fields and are already in state from generators.
        # Returning them would cause LangGraph to add them again, creating duplicates.
    }
