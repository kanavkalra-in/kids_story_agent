from langchain_core.messages import HumanMessage, SystemMessage
from app.services.llm import get_llm
from app.agents.state import StoryState
from app.config import settings
from typing import Dict, List
import re
import logging

logger = logging.getLogger(__name__)


def image_prompter_node(state: StoryState) -> Dict:
    """Extract key scenes from story and create DALL-E-optimized image prompts"""
    job_id = state.get("job_id", "unknown")
    # Use Ollama for image prompt generation
    llm = get_llm(provider="ollama")
    
    # Log which LLM provider is being used
    logger.info(f"Job {job_id}: Image prompter using Ollama (model: {settings.ollama_model})")
    
    num_images = state.get("num_illustrations", 3)
    story_text = state.get("story_text", "")
    
    logger.info(f"Job {job_id}: Generating {num_images} image prompts from story (length: {len(story_text)} chars)")
    
    if not story_text:
        error_msg = "No story text available for image prompt generation"
        logger.error(f"Job {job_id}: {error_msg}")
        return {
            "error": error_msg,
        }
    
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
    
    user_prompt = f"""Given this children's story, identify {num_images} key scenes that would make great illustrations.

Story:
{story_text}

For each scene, provide:
1. A brief scene description (what's happening)
2. A detailed DALL-E prompt optimized for image generation

Format your response as:
SCENE 1:
Description: [brief description]
Prompt: [detailed DALL-E prompt]

SCENE 2:
Description: [brief description]
Prompt: [detailed DALL-E prompt]

...and so on for {num_images} scenes.
"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    
    logger.debug(f"Job {job_id}: Calling LLM to generate image prompts")
    response = llm.invoke(messages)
    content = response.content
    logger.debug(f"Job {job_id}: LLM response length: {len(content)} chars")
    
    # Parse scenes
    scenes = []
    scene_pattern = r"SCENE\s+\d+:\s*Description:\s*(.+?)\s*Prompt:\s*(.+?)(?=SCENE\s+\d+:|$)"
    matches = re.finditer(scene_pattern, content, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        description = match.group(1).strip()
        prompt = match.group(2).strip()
        scenes.append({
            "description": description,
            "prompt": prompt,
        })
    
    # Fallback parsing if regex doesn't work
    if not scenes:
        logger.warning(f"Job {job_id}: Primary regex parsing failed, trying fallback parsing")
        # Try simpler parsing
        parts = re.split(r"SCENE\s+\d+:", content, flags=re.IGNORECASE)
        for part in parts[1:]:  # Skip first empty part
            lines = part.strip().split("\n")
            description = ""
            prompt = ""
            in_prompt = False
            
            for line in lines:
                if line.strip().startswith("Description:"):
                    description = line.replace("Description:", "").strip()
                elif line.strip().startswith("Prompt:"):
                    in_prompt = True
                    prompt = line.replace("Prompt:", "").strip()
                elif in_prompt:
                    prompt += " " + line.strip()
            
            if description and prompt:
                scenes.append({
                    "description": description,
                    "prompt": prompt,
                })
    
    # Ensure we have the right number of scenes
    if len(scenes) < num_images:
        logger.warning(f"Job {job_id}: Only parsed {len(scenes)} scenes, expected {num_images}. Adding generic scenes.")
        # If we got fewer scenes, duplicate the last one or create generic ones
        while len(scenes) < num_images:
            scenes.append({
                "description": f"Scene from the story",
                "prompt": f"Children's book illustration, colorful, whimsical, friendly, scene from a children's story",
            })
    elif len(scenes) > num_images:
        logger.info(f"Job {job_id}: Parsed {len(scenes)} scenes, truncating to {num_images}")
        scenes = scenes[:num_images]
    
    # Extract just the prompts for the state
    image_prompts = [scene["prompt"] for scene in scenes]
    image_metadata = [
        {
            "description": scene["description"],
            "prompt": scene["prompt"],
        }
        for scene in scenes
    ]
    
    logger.info(f"Job {job_id}: Successfully generated {len(image_prompts)} image prompts")
    
    return {
        "image_prompts": image_prompts,
        "image_metadata": image_metadata,
    }
