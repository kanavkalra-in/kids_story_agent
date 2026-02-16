"""
Human Review Gate Node — LangGraph interrupt() for human-in-the-loop.

This node uses LangGraph's ``interrupt()`` to pause graph execution and
present a review package to a human reviewer. The graph state is persisted
to the PostgresSaver checkpointer.

The graph resumes when the API calls ``graph.ainvoke(Command(resume=...))``
with the reviewer's decision.
"""

from langgraph.types import interrupt

from app.agents.state import StoryState
from app.constants import REVIEW_AUTO_REJECTED
import logging

logger = logging.getLogger(__name__)


def human_review_gate_node(state: StoryState) -> dict:
    """
    Pause graph execution for human review.

    If guardrails hard-failed and auto-reject is enabled, this node
    won't be reached (the graph routes to mark_auto_rejected instead).

    The ``interrupt()`` call:
    1. Serializes the review package as the interrupt value
    2. Saves graph state to the checkpointer (PostgresSaver)
    3. Returns control to the caller

    The graph resumes when the caller invokes:
        graph.ainvoke(
            Command(resume={"decision": "approved|rejected", "comment": "...", "reviewer_id": "..."}),
            config={"configurable": {"thread_id": job_id}}
        )
    """
    job_id = state.get("job_id", "unknown")

    # Build review package shown to the human reviewer
    review_package = {
        "job_id": job_id,
        "story_title": state.get("story_title"),
        "story_text": state.get("story_text"),
        "age_group": state.get("age_group"),
        "evaluation_scores": state.get("evaluation_scores"),
        "guardrail_passed": state.get("guardrail_passed"),
        "guardrail_summary": state.get("guardrail_summary"),
        "guardrail_violations": state.get("guardrail_violations", []),
        "image_urls": state.get("image_urls", []),
        "video_urls": state.get("video_urls", []),
    }

    logger.info(f"Job {job_id}: Entering human review gate — graph will pause here")

    # GRAPH PAUSES HERE — state saved to PostgresSaver checkpointer
    decision = interrupt(review_package)

    # Resumes here when Command(resume=...) is called
    review_decision = decision.get("decision", "rejected")
    review_comment = decision.get("comment", "")
    reviewer_id = decision.get("reviewer_id", "")

    logger.info(
        f"Job {job_id}: Human review decision received — "
        f"decision={review_decision}, reviewer={reviewer_id}"
    )

    return {
        "review_decision": review_decision,
        "review_comment": review_comment,
        "reviewer_id": reviewer_id,
    }
