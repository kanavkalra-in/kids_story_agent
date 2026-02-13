from langchain_core.messages import HumanMessage, SystemMessage
from app.services.llm import get_llm
from app.agents.state import StoryState
from app.config import settings
from typing import Dict
import logging

logger = logging.getLogger(__name__)


def get_age_group_instructions(age_group: str) -> str:
    """Get age-appropriate writing instructions"""
    age_instructions = {
        "3-5": """
        - Use very simple words (3-4 letter words when possible)
        - Keep sentences short (5-8 words max)
        - Use repetition and rhythm
        - Focus on friendly, safe themes (animals, friendship, helping)
        - Include sensory details (colors, sounds, textures)
        - Make it fun and playful
        """,
        "6-8": """
        - Use moderate vocabulary (some 5-6 letter words)
        - Sentences can be 8-12 words
        - Include simple dialogue
        - Themes: adventure, friendship, problem-solving, discovery
        - Add some descriptive details
        - Include a clear beginning, middle, and end
        """,
        "9-12": """
        - Use richer vocabulary and varied sentence structure
        - Sentences can be 10-15 words
        - Include dialogue and character development
        - Themes: adventure, mystery, growth, overcoming challenges
        - More complex plots with multiple events
        - Include character emotions and motivations
        """,
    }
    return age_instructions.get(age_group, age_instructions["6-8"])


def story_writer_node(state: StoryState) -> Dict:
    """Generate the story text based on prompt and age group"""
    job_id = state.get("job_id", "unknown")
    # Use Ollama for story writing
    llm = get_llm(provider="ollama")
    
    # Log which LLM provider is being used
    logger.info(f"Job {job_id}: Story writer using Ollama (model: {settings.ollama_model})")
    
    age_instructions = get_age_group_instructions(state["age_group"])
    
    system_prompt = f"""You are a children's story writer. Create an engaging, age-appropriate story.

Age Group: {state['age_group']} years old

Writing Guidelines:
{age_instructions}

Requirements:
- The story should be 300-500 words
- Include a clear title
- Make it engaging and fun
- Ensure it's appropriate for the age group
- Include vivid scenes that can be illustrated
"""
    
    user_prompt = f"""Write a children's story based on this prompt:

{state['prompt']}

Please provide:
1. A title for the story
2. The full story text

Format your response as:
TITLE: [story title]

STORY:
[story text here]
"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    
    response = llm.invoke(messages)
    story_content = response.content
    
    # Parse title and story
    lines = story_content.split("\n")
    title = None
    story_text = []
    in_story = False
    
    for line in lines:
        if line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
        elif line.startswith("STORY:") or in_story:
            if line.startswith("STORY:"):
                in_story = True
                continue
            story_text.append(line.strip())
    
    # Fallback parsing if format is different
    if not title:
        # Try to extract first line as title
        first_line = lines[0].strip()
        if len(first_line) < 100 and not first_line.startswith("Once"):
            title = first_line
            story_text = "\n".join(lines[1:]).strip()
        else:
            title = "A Wonderful Story"
            story_text = "\n".join(lines).strip()
    
    if isinstance(story_text, list):
        story_text = "\n".join(story_text).strip()
    
    if not story_text:
        story_text = story_content.strip()
    
    return {
        "story_title": title or "A Wonderful Story",
        "story_text": story_text,
    }
