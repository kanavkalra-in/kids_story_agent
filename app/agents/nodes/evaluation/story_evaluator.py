"""
Story Evaluator Node — LLM-based quality scoring.

Evaluates a story on moral, theme, emotional positivity, age-appropriateness,
and educational value. Produces scores (1–10) and a narrative summary.
Runs in parallel with guardrail nodes via LangGraph Send.
"""

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from app.services.llm import get_llm
from app.agents.state import StoryState
import logging

logger = logging.getLogger(__name__)


class StoryEvalOutput(BaseModel):
    """Structured evaluation scores from the LLM."""
    moral_score: float = Field(ge=1, le=10, description="Moral/ethical quality of the story")
    theme_appropriateness: float = Field(ge=1, le=10, description="Theme fit for the target age group")
    emotional_positivity: float = Field(ge=1, le=10, description="Emotional warmth and positivity")
    age_appropriateness: float = Field(ge=1, le=10, description="Language and content match for age")
    educational_value: float = Field(ge=1, le=10, description="Educational takeaways present")
    evaluation_summary: str = Field(description="Brief narrative summary of the quality assessment")


EVAL_SYSTEM_PROMPT = """You are a children's content quality evaluator for a kids story platform.
Score the following story on each dimension from 1 to 10.
Target age group: {age_group}.

Scoring rubric:
- moral_score: Does the story teach positive values? (kindness, honesty, courage, sharing, empathy)
- theme_appropriateness: Is the theme suitable, engaging, and developmentally appropriate for the age group?
- emotional_positivity: Does the story evoke warmth, joy, hope, and comfort? (not fear, anxiety, sadness)
- age_appropriateness: Is the vocabulary, sentence structure, and content complexity right for the age?
- educational_value: Does the child learn something valuable? (social skills, knowledge, problem-solving, empathy)

Be strict — this content goes directly to children. Provide an honest evaluation_summary with specific examples from the story."""


# Weights for computing the weighted overall score
EVAL_WEIGHTS = {
    "moral": 0.25,
    "theme": 0.20,
    "emotional": 0.25,
    "age": 0.20,
    "edu": 0.10,
}


def story_evaluator_node(state: StoryState) -> dict:
    """
    Evaluate story quality on moral, theme, emotional positivity, etc.

    This node is invoked via LangGraph ``Send`` from the assembler.
    It returns evaluation scores and an empty violations list (evaluator
    does not produce guardrail violations — that's the guardrail node's job).
    """
    job_id = state.get("job_id", "unknown")
    story_text = state.get("story_text", "")
    story_title = state.get("story_title", "")
    age_group = state.get("age_group", "6-8")

    logger.info(f"Job {job_id}: Running story evaluation")

    llm = get_llm()
    structured_llm = llm.with_structured_output(StoryEvalOutput)

    system_prompt = EVAL_SYSTEM_PROMPT.format(age_group=age_group)
    human_content = f"Title: {story_title}\n\n{story_text}"
    logger.info(
        f"Job {job_id}: [StoryEval] Prompt → system: {system_prompt[:200]}... | "
        f"story ({len(story_text)} chars): {story_text[:300]}..."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_content),
    ]
    output = structured_llm.invoke(messages)

    # Immediately convert Pydantic model to plain Python types to avoid serialization issues
    # with LangGraph's checkpointer. Extract all values before building return dict.
    moral_score = float(output.moral_score)
    theme_appropriateness = float(output.theme_appropriateness)
    emotional_positivity = float(output.emotional_positivity)
    age_appropriateness = float(output.age_appropriateness)
    educational_value = float(output.educational_value)
    evaluation_summary = str(output.evaluation_summary)
    
    # Explicitly clear the Pydantic model reference immediately after extraction
    # to prevent serialization issues with LangGraph's checkpointer
    del output

    logger.info(
        f"Job {job_id}: [StoryEval] Output → "
        f"moral={moral_score}, theme={theme_appropriateness}, "
        f"emotional={emotional_positivity}, age={age_appropriateness}, "
        f"edu={educational_value}, "
        f"summary={evaluation_summary}"
    )

    overall = round(
        moral_score * EVAL_WEIGHTS["moral"]
        + theme_appropriateness * EVAL_WEIGHTS["theme"]
        + emotional_positivity * EVAL_WEIGHTS["emotional"]
        + age_appropriateness * EVAL_WEIGHTS["age"]
        + educational_value * EVAL_WEIGHTS["edu"],
        2,
    )

    logger.info(
        f"Job {job_id}: Evaluation complete — overall score {overall}/10 "
        f"(moral={moral_score}, theme={theme_appropriateness}, "
        f"emotional={emotional_positivity}, age={age_appropriateness}, "
        f"edu={educational_value})"
    )

    return {
        "evaluation_scores": {
            "moral_score": moral_score,
            "theme_appropriateness": theme_appropriateness,
            "emotional_positivity": emotional_positivity,
            "age_appropriateness": age_appropriateness,
            "educational_value": educational_value,
            "overall_score": overall,
            "evaluation_summary": evaluation_summary,
        },
        # Evaluator produces no violations — return empty lists for reducers
        "guardrail_violations": [],
        "image_urls_final": [],
        "video_urls_final": [],
    }
