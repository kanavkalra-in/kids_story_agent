from app.agents.state import StoryState
from app.agents.nodes.generation.prompter_utils import generate_media_prompts, StoryGenerationError
import logging

logger = logging.getLogger(__name__)


def image_prompter_node(state: StoryState) -> dict:
    """Extract key scenes from story and create DALL-E-optimized image prompts"""
    job_id = state.get("job_id", "unknown")
    
    # CRITICAL: Get num_illustrations from state - if missing, this is an error
    num_illustrations = state.get("num_illustrations")
    if num_illustrations is None:
        error_msg = f"Job {job_id}: num_illustrations is missing from state! This will cause incorrect behavior."
        logger.error(error_msg)
        raise StoryGenerationError(error_msg)
    
    num_images = num_illustrations
    logger.info(
        f"Job {job_id}: [IMAGE_PROMPTER] Starting - num_illustrations from state={num_illustrations}, "
        f"using num_images={num_images}, generate_images={state.get('generate_images', False)}"
    )
    
    system_prompt = """You are an expert at creating image generation prompts. 
Your task is to identify the most visually interesting and important scenes from a children's story 
and create detailed, DALL-E-optimized prompts for each scene.

Guidelines for DALL-E prompts:
- Be specific and descriptive
- Include style: "children's book illustration, colorful, whimsical, friendly"
- Mention the mood/atmosphere
- Include key visual elements (characters, setting, actions)
- Keep prompts under 200 words
- Make them appropriate for children (no scary or inappropriate content)
"""
    
    user_prompt = """Given this children's story, identify EXACTLY {num_items} key scene(s) that would make great illustration(s).

Story:
{story_text}

For each scene, provide:
1. A brief scene description (what's happening)
2. A detailed DALL-E prompt optimized for image generation

CRITICAL REQUIREMENTS:
- You MUST provide EXACTLY {num_items} scene(s) - no more, no less
- If {num_items} is 1, provide ONLY 1 scene
- If {num_items} is 3, provide EXACTLY 3 scenes
- Do NOT provide 4 scenes when asked for 1
- Do NOT provide more scenes than requested
- Your response must contain exactly {num_items} items in the scenes array

The number {num_items} is the exact count you must return. Count carefully and ensure your scenes array has exactly {num_items} elements.
"""
    
    return generate_media_prompts(
        state=state,
        media_type="image",
        num_items=num_images,
        system_prompt_template=system_prompt,
        user_prompt_template=user_prompt,
    )
