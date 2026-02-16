"""
Input Moderator Node — Prevention layer using OpenAI Moderation API.

Checks the user's story prompt BEFORE any generation begins.
Uses OpenAI's native Moderation API (~50ms, free) to catch violence,
sexual, hate, self-harm, and harassment content at the input stage.

If the prompt is flagged, sets ``input_moderation_passed = False``
and the graph routes to ``mark_auto_rejected`` without invoking any LLMs.
"""

from app.agents.state import StoryState
from app.services.moderation import check_openai_moderation
from app.constants import SEVERITY_HARD
import logging

logger = logging.getLogger(__name__)


def input_moderator_node(state: StoryState) -> dict:
    """
    Check user input prompt for inappropriate content before generation.

    Uses OpenAI Moderation API as a fast pre-filter.

    Returns:
        State updates with input_moderation_passed flag and any violations.
    """
    job_id = state.get("job_id", "unknown")
    prompt = state.get("prompt", "")

    logger.info(f"Job {job_id}: Running input moderation on user prompt")

    # Run OpenAI Moderation API on the input prompt
    violations = check_openai_moderation(prompt)

    if violations:
        # Re-tag as input violations
        for v in violations:
            v["guardrail_name"] = "input_openai_moderation"
            v["media_type"] = "input"
        logger.warning(
            f"Job {job_id}: Input prompt flagged by OpenAI Moderation API"
        )

    has_hard = any(v["severity"] == SEVERITY_HARD for v in violations)
    input_passed = not has_hard

    if input_passed:
        logger.info(f"Job {job_id}: Input moderation PASSED")
    else:
        logger.warning(
            f"Job {job_id}: Input moderation FAILED — "
            f"{len(violations)} violation(s), blocking generation"
        )

    return {
        "input_moderation_passed": input_passed,
        "guardrail_violations": violations,
        "guardrail_summary": (
            None if input_passed
            else f"Input prompt blocked: {'; '.join(v['detail'] for v in violations)}"
        ),
    }
