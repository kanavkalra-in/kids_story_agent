from app.agents.state import StoryState
from app.agents.prompter_utils import generate_media_prompts


def video_prompter_node(state: StoryState) -> dict:
    """Extract key scenes from story and create Sora-optimized video prompts"""
    num_videos = state.get("num_illustrations", 3)  # Use same count as illustrations
    
    system_prompt = """You are an expert at creating video generation prompts for Sora. 
Your task is to identify the most visually interesting and dynamic scenes from a children's story 
and create detailed, Sora-optimized prompts for each scene.

Guidelines for Sora video prompts:
- Be specific and descriptive about motion and action
- Include style: "children's book animation, colorful, whimsical, friendly"
- Mention the mood/atmosphere
- Include key visual elements (characters, setting, actions)
- Describe movement and dynamics (e.g., "a character running", "leaves falling", "water flowing")
- Keep prompts under 200 words
- Make them appropriate for children (no scary or inappropriate content)
- Focus on scenes that benefit from motion (not static scenes)
- Videos will be maximum 10 seconds long, so design prompts for concise, impactful scenes
"""
    
    user_prompt = """Given this children's story, identify {num_items} key scenes that would make great short videos (maximum 10 seconds each).

Story:
{story_text}

For each scene, provide:
1. A brief scene description (what's happening with motion)
2. A detailed Sora prompt optimized for video generation (emphasize movement and action)

IMPORTANT: Each video will be maximum 10 seconds long. Design prompts for concise, impactful scenes that can be effectively conveyed within this duration. Focus on a single key moment or action per scene.

You must provide exactly {num_items} scenes.
"""
    
    return generate_media_prompts(
        state=state,
        media_type="video",
        num_items=num_videos,
        system_prompt_template=system_prompt,
        user_prompt_template=user_prompt,
    )
