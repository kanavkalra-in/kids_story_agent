from app.agents.state import StoryState
from app.agents.nodes.generation.prompter_utils import generate_media_prompts


def image_prompter_node(state: StoryState) -> dict:
    """Extract key scenes from story and create DALL-E-optimized image prompts"""
    num_images = state.get("num_illustrations", 3)
    
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
    
    user_prompt = """Given this children's story, identify {num_items} key scenes that would make great illustrations.

Story:
{story_text}

For each scene, provide:
1. A brief scene description (what's happening)
2. A detailed DALL-E prompt optimized for image generation

You must provide exactly {num_items} scenes.
"""
    
    return generate_media_prompts(
        state=state,
        media_type="image",
        num_items=num_images,
        system_prompt_template=system_prompt,
        user_prompt_template=user_prompt,
    )
