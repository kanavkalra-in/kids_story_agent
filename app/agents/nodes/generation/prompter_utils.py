"""
Shared utilities for image and video prompt generation.
Consolidates duplicate parsing and LLM interaction logic.
"""
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from app.services.llm import get_llm
from app.agents.state import StoryState
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class StoryGenerationError(Exception):
    """Custom exception for story generation failures"""
    pass


class Scene(BaseModel):
    """A single scene with description and prompt."""
    description: str
    prompt: str


class ScenesOutput(BaseModel):
    """Output containing multiple scenes."""
    scenes: list[Scene]


def generate_media_prompts(
    state: StoryState,
    media_type: str,  # "image" or "video"
    num_items: int,
    system_prompt_template: str,
    user_prompt_template: str,
) -> dict:
    """
    Generic function to generate media prompts (images or videos).
    Uses structured output to ensure reliable parsing.
    
    Args:
        state: Current workflow state
        media_type: "image" or "video"
        num_items: Number of prompts to generate
        system_prompt_template: System prompt template
        user_prompt_template: User prompt template (should include {num_items} and {story_text} placeholders)
        
    Returns:
        Dict with prompts and metadata lists
    """
    job_id = state.get("job_id", "unknown")
    
    # Check if generation is enabled
    generate_flag = state.get(f"generate_{media_type}s", False)
    if not generate_flag:
        logger.info(f"Job {job_id}: {media_type} generation disabled, skipping {media_type} prompter")
        return {
            f"{media_type}_prompts": [],
            f"{media_type}_descriptions": [],
        }
    
    llm = get_llm()
    logger.info(f"Job {job_id}: {media_type.capitalize()} prompter using LLM provider: {settings.llm_provider}")
    
    story_text = state.get("story_text", "")
    
    logger.info(f"Job {job_id}: Generating {num_items} {media_type} prompts from story (length: {len(story_text)} chars)")
    
    if not story_text:
        error_msg = f"No story text available for {media_type} prompt generation"
        logger.error(f"Job {job_id}: {error_msg}")
        raise StoryGenerationError(error_msg)
    
    # Format prompts
    system_prompt = system_prompt_template
    user_prompt = user_prompt_template.format(num_items=num_items, story_text=story_text)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    
    logger.debug(f"Job {job_id}: Calling LLM to generate {media_type} prompts with structured output")
    
    # Use structured output to get reliable parsing
    structured_llm = llm.with_structured_output(ScenesOutput)
    output = structured_llm.invoke(messages)
    
    scenes = output.scenes
    
    # Validate we got the right number of scenes
    if len(scenes) < num_items:
        error_msg = f"Only generated {len(scenes)} {media_type} scenes, expected {num_items}. LLM did not generate enough scenes."
        logger.error(f"Job {job_id}: {error_msg}")
        raise StoryGenerationError(error_msg)
    elif len(scenes) > num_items:
        logger.info(f"Job {job_id}: Generated {len(scenes)} {media_type} scenes, truncating to {num_items}")
        scenes = scenes[:num_items]
    
    # Extract prompts and descriptions as separate parallel lists.
    # Descriptions are stored in a non-reducer state field so they don't
    # accumulate with the generator metadata (which uses operator.add).
    prompts = [scene.prompt for scene in scenes]
    descriptions = [scene.description for scene in scenes]
    
    logger.info(f"Job {job_id}: Successfully generated {len(prompts)} {media_type} prompts")
    
    return {
        f"{media_type}_prompts": prompts,
        f"{media_type}_descriptions": descriptions,
    }
