"""
Rejection Handler Nodes — mark stories as auto-rejected or human-rejected.

These are lightweight terminal nodes that log the rejection reason.
Actual DB status updates are handled in story_tasks.py after the graph completes.
"""

from app.agents.state import StoryState
from app.constants import REVIEW_AUTO_REJECTED, REVIEW_REJECTED
import logging

logger = logging.getLogger(__name__)


def mark_auto_rejected_node(state: StoryState) -> dict:
    """
    Auto-rejected due to hard guardrail violations.
    No human review was needed — the system decided automatically.
    """
    job_id = state.get("job_id", "unknown")
    guardrail_summary = state.get("guardrail_summary", "No summary available")

    logger.warning(
        f"Job {job_id}: AUTO-REJECTED due to hard guardrail violations.\n"
        f"Summary:\n{guardrail_summary}"
    )

    return {
        "review_decision": REVIEW_AUTO_REJECTED,
        "review_comment": f"Auto-rejected by guardrails.\n{guardrail_summary}",
        "reviewer_id": "system_guardrail",
    }


def mark_rejected_node(state: StoryState) -> dict:
    """
    Human reviewer rejected the story.
    The reviewer's comment and ID are already in state from human_review_gate.
    """
    job_id = state.get("job_id", "unknown")
    reviewer_id = state.get("reviewer_id", "unknown")
    review_comment = state.get("review_comment", "")

    logger.info(
        f"Job {job_id}: REJECTED by reviewer {reviewer_id}. "
        f"Comment: {review_comment or 'none'}"
    )

    # review_decision is already set by human_review_gate_node
    return {}
