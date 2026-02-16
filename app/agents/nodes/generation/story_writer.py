from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from app.services.llm import get_llm
from app.agents.state import StoryState
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class StoryOutput(BaseModel):
    """Output containing story title and text."""
    title: str
    story_text: str


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


def story_writer_node(state: StoryState) -> dict:
    """Generate the story text based on prompt and age group"""
    job_id = state.get("job_id", "unknown")
    llm = get_llm("ollama")
    
    logger.info(f"Job {job_id}: Story writer using LLM provider: {settings.llm_provider}")
    
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
"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    
    # Use structured output to get reliable parsing
    structured_llm = llm.with_structured_output(StoryOutput)
    output = structured_llm.invoke(messages)
    
    # Immediately convert Pydantic model to plain Python types to avoid serialization issues
    # with LangGraph's checkpointer. Extract data before returning state.
    story_title = str(output.title) if output.title else "A Wonderful Story"
    story_text = str(output.story_text)
    
    # Explicitly clear the Pydantic model reference to prevent serialization issues
    del output
    
    return {
        "story_title": story_title,
        "story_text": story_text,
    }
