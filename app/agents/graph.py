"""
LangGraph workflow for story generation with evaluation, guardrails,
and human-in-the-loop review.

Guardrails (single standard framework — OpenAI Moderation API):

- **OpenAI Moderation API** — Fast pre-filter on input + output (~50ms, free)
- **Regex PII** — Email, phone, SSN, credit card detection
- **Custom LLM prompts** — Domain-specific kids content safety analysis

Parallelism strategy (all handled natively by LangGraph):

1. **Input moderation** — ``input_moderator`` checks the user's prompt BEFORE
   generation via OpenAI Moderation API. If blocked, routes to
   ``mark_auto_rejected`` without invoking any LLMs.

2. **Prompter parallelism** — Static edges: ``story_writer`` has edges to
   both ``image_prompter`` and ``video_prompter``; LangGraph runs them in
   parallel and waits for both before proceeding.

3. **Generator fan-out** — Dynamic ``Send``: Both prompters route to generators
   by inspecting the prompt lists and emitting one ``Send`` per image/video prompt.

4. **Guardrail fan-out** — From the assembler, ``route_to_guardrails`` emits
   one ``Send`` per: story_evaluator, story_guardrail, each image_guardrail,
   each video_guardrail. All run in parallel.

5. **Human-in-the-loop** — ``human_review_gate`` uses LangGraph's ``interrupt()``
   to pause execution. State is checkpointed to PostgresSaver. The graph resumes
   when the review API calls ``Command(resume=...)``.

Graph shape:

                        input_moderator (OpenAI Moderation API)
                                │
                    ┌── input safe? ──┐
                    │no               │yes
           mark_auto_rejected    story_writer
                    │               ├──► image_prompter ──┐
                   END              └──► video_prompter ──┤
                                                          ▼ (fan-in)
                                ┌──► generate_single_image (×N) ──┐
                                └──► generate_single_video (×M) ──┤
                                                                  ▼
                                                              assembler
                                                                  │
                                            route_to_guardrails (fan-out)
                                          /       |            |           \\
                              story_eval  story_guard  img_guard(×N)  vid_guard(×M)
                                          \\      |            |           /
                                            guardrail_aggregator (fan-in)
                                                                  │
                                            ┌── has hard violations? ──┐
                                            │yes                       │no
                                   mark_auto_rejected         human_review_gate
                                            │                         │
                                           END              ┌── decision? ──┐
                                                            │               │
                                                      [approved]       [rejected]
                                                            │               │
                                                       publisher      mark_rejected
                                                            │               │
                                                           END             END

    story_guardrail pipeline (3 layers):
        Layer 0: OpenAI Moderation API (fast pre-filter)
        Layer 1: Regex PII detection (emails, phones, SSNs, credit cards)
        Layer 2: Custom LLM safety analysis (fear, violence, brand, political, religious)
"""

from langgraph.graph import StateGraph, END
from langgraph.types import Send
from app.agents.state import StoryState
from app.agents.nodes import (
    # Generation phase
    story_writer_node,
    image_prompter_node,
    video_prompter_node,
    image_generator_node,
    video_generator_node,
    assembler_node,
    # Input Moderation (prevention layer)
    input_moderator_node,
    # Evaluation & Guardrails phase
    story_evaluator_node,
    story_guardrail_node,
    image_guardrail_with_retry_node,
    video_guardrail_with_retry_node,
    guardrail_aggregator_node,
    # Review & Publish phase
    human_review_gate_node,
    publisher_node,
    mark_auto_rejected_node,
    mark_rejected_node,
)
from app.config import settings
from typing import Union
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------


def route_after_input_moderation(state: StoryState) -> str:
    """
    After input moderation: if prompt was blocked, auto-reject immediately.
    Otherwise proceed to story generation.
    """
    if state.get("input_moderation_passed", True) is False:
        logger.info(
            f"Job {state.get('job_id')}: Input blocked → auto-reject "
            f"(skipping generation entirely)"
        )
        return "mark_auto_rejected"
    return "story_writer"


def route_to_image_generators(state: StoryState) -> Union[list[Send], str]:
    """
    Fan-out from image_prompter to individual image generator instances.

    Creates one ``Send`` per image prompt. Only includes the minimal state
    keys needed by the generator node.
    """
    sends: list[Send] = []

    job_id = state.get("job_id", "unknown")
    image_prompts = state.get("image_prompts", [])
    image_descriptions = state.get("image_descriptions", [])
    generate_images = state.get("generate_images", False)

    for i, prompt in enumerate(image_prompts):
        desc = image_descriptions[i] if i < len(image_descriptions) else ""
        sends.append(Send("generate_single_image", {
            "job_id": job_id,
            "generate_images": generate_images,
            "_current_prompt": prompt,
            "_current_index": i,
            "_current_description": desc,
        }))

    if not sends:
        return "assembler"

    return sends


def route_to_video_generators(state: StoryState) -> Union[list[Send], str]:
    """
    Fan-out from video_prompter to individual video generator instances.

    Creates one ``Send`` per video prompt. Only includes the minimal state
    keys needed by the generator node.
    """
    sends: list[Send] = []

    job_id = state.get("job_id", "unknown")
    video_prompts = state.get("video_prompts", [])
    video_descriptions = state.get("video_descriptions", [])
    generate_videos = state.get("generate_videos", False)

    for i, prompt in enumerate(video_prompts):
        desc = video_descriptions[i] if i < len(video_descriptions) else ""
        sends.append(Send("generate_single_video", {
            "job_id": job_id,
            "generate_videos": generate_videos,
            "_current_prompt": prompt,
            "_current_index": i,
            "_current_description": desc,
        }))

    if not sends:
        return "assembler"

    return sends


def route_to_guardrails(state: StoryState) -> list[Send]:
    """
    Fan-out from assembler to all guardrail checks in parallel.

    Creates Sends for:
    - story_evaluator (quality scoring)
    - story_guardrail (text safety)
    - image_guardrail_with_retry (×N, one per image)
    - video_guardrail_with_retry (×M, one per video)

    All run concurrently and fan-in to guardrail_aggregator.
    """
    sends: list[Send] = []
    job_id = state.get("job_id", "unknown")
    age_group = state.get("age_group", "6-8")

    # 1. Story evaluator (quality scores)
    sends.append(Send("story_evaluator", {
        "job_id": job_id,
        "story_text": state.get("story_text"),
        "story_title": state.get("story_title"),
        "age_group": age_group,
    }))

    # 2. Story guardrail (text safety)
    sends.append(Send("story_guardrail", {
        "job_id": job_id,
        "story_text": state.get("story_text"),
        "age_group": age_group,
    }))

    # 3. Per-image guardrails (with retry/regeneration)
    image_prompts = state.get("image_prompts", [])
    for i, url in enumerate(state.get("image_urls", [])):
        sends.append(Send("image_guardrail_with_retry", {
            "job_id": job_id,
            "age_group": age_group,
            "_guardrail_media_url": url,
            "_guardrail_media_index": i,
            "_guardrail_original_prompt": image_prompts[i] if i < len(image_prompts) else "",
        }))

    # 4. Per-video guardrails (prompt moderation + retry)
    video_prompts = state.get("video_prompts", [])
    for i, url in enumerate(state.get("video_urls", [])):
        sends.append(Send("video_guardrail_with_retry", {
            "job_id": job_id,
            "age_group": age_group,
            "_guardrail_media_url": url,
            "_guardrail_media_index": i,
            "_guardrail_original_prompt": video_prompts[i] if i < len(video_prompts) else "",
        }))

    logger.info(
        f"Job {job_id}: Routing to {len(sends)} parallel guardrail checks "
        f"(1 evaluator + 1 story guardrail + "
        f"{len(state.get('image_urls', []))} image + "
        f"{len(state.get('video_urls', []))} video)"
    )

    return sends


def route_after_aggregator(state: StoryState) -> str:
    """
    After guardrail aggregation: auto-reject on hard violations,
    otherwise proceed to human review.
    """
    if not state.get("guardrail_passed", True):
        logger.info(f"Job {state.get('job_id')}: Hard violations found → auto-reject")
        return "mark_auto_rejected"
    logger.info(f"Job {state.get('job_id')}: Guardrails passed → human review")
    return "human_review_gate"


def route_after_review(state: StoryState) -> str:
    """Route based on human review decision."""
    decision = state.get("review_decision", "rejected")
    if decision == "approved":
        return "publisher"
    return "mark_rejected"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _get_checkpointer():
    """
    Create a PostgresSaver checkpointer for interrupt() support.

    PostgresSaver is required for human-in-the-loop workflows to survive
    worker restarts. Raises on connection errors — ensure PostgreSQL
    is running and the connection string is valid.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    conn_string = settings.checkpointer_conn_string

    if not conn_string:
        # Derive sync connection string from async database_url
        # asyncpg → psycopg2 for the checkpointer
        conn_string = settings.database_url.replace(
            "postgresql+asyncpg://", "postgresql://"
        )

    checkpointer = PostgresSaver.from_conn_string(conn_string)
    checkpointer.setup()
    logger.info("Using PostgresSaver checkpointer for human-in-the-loop support")
    return checkpointer


def create_story_graph() -> StateGraph:
    """Build and compile the LangGraph workflow with evaluation, guardrails, and HITL."""

    workflow = StateGraph(StoryState)

    # ── Input Moderation node (prevention layer) ──
    workflow.add_node("input_moderator", input_moderator_node)

    # ── Generation nodes ──
    workflow.add_node("story_writer", story_writer_node)
    workflow.add_node("image_prompter", image_prompter_node)
    workflow.add_node("video_prompter", video_prompter_node)
    workflow.add_node("generate_single_image", image_generator_node)
    workflow.add_node("generate_single_video", video_generator_node)
    workflow.add_node("assembler", assembler_node)

    # ── Evaluation & Guardrail nodes ──
    workflow.add_node("story_evaluator", story_evaluator_node)
    workflow.add_node("story_guardrail", story_guardrail_node)
    workflow.add_node("image_guardrail_with_retry", image_guardrail_with_retry_node)
    workflow.add_node("video_guardrail_with_retry", video_guardrail_with_retry_node)
    workflow.add_node("guardrail_aggregator", guardrail_aggregator_node)

    # ── Human review & publish nodes ──
    workflow.add_node("human_review_gate", human_review_gate_node)
    workflow.add_node("publisher", publisher_node)
    workflow.add_node("mark_auto_rejected", mark_auto_rejected_node)
    workflow.add_node("mark_rejected", mark_rejected_node)

    # ── Edges: Input moderation → generation pipeline ──
    workflow.set_entry_point("input_moderator")

    # input_moderator → story_writer (if safe) or mark_auto_rejected (if blocked)
    workflow.add_conditional_edges("input_moderator", route_after_input_moderation,
                                  ["story_writer", "mark_auto_rejected"])

    # story_writer → both prompters (static edges, always run in parallel)
    workflow.add_edge("story_writer", "image_prompter")
    workflow.add_edge("story_writer", "video_prompter")

    # Each prompter routes only to its own generators (avoids duplicate Sends)
    workflow.add_conditional_edges("image_prompter", route_to_image_generators,
                                  ["generate_single_image", "assembler"])
    workflow.add_conditional_edges("video_prompter", route_to_video_generators,
                                  ["generate_single_video", "assembler"])

    # All generators → assembler (fan-in)
    workflow.add_edge("generate_single_image", "assembler")
    workflow.add_edge("generate_single_video", "assembler")

    # ── Edges: Guardrail pipeline (NEW) ──

    # assembler → fan-out to all guardrails in parallel
    workflow.add_conditional_edges("assembler", route_to_guardrails,
                                  ["story_evaluator", "story_guardrail",
                                   "image_guardrail_with_retry",
                                   "video_guardrail_with_retry"])

    # All guardrails → fan-in to aggregator
    workflow.add_edge("story_evaluator", "guardrail_aggregator")
    workflow.add_edge("story_guardrail", "guardrail_aggregator")
    workflow.add_edge("image_guardrail_with_retry", "guardrail_aggregator")
    workflow.add_edge("video_guardrail_with_retry", "guardrail_aggregator")

    # Aggregator → auto-reject OR human review
    workflow.add_conditional_edges("guardrail_aggregator", route_after_aggregator,
                                  ["mark_auto_rejected", "human_review_gate"])

    # Human review → approve OR reject
    workflow.add_conditional_edges("human_review_gate", route_after_review,
                                  ["publisher", "mark_rejected"])

    # Terminal edges
    workflow.add_edge("publisher", END)
    workflow.add_edge("mark_auto_rejected", END)
    workflow.add_edge("mark_rejected", END)

    # ── Compile with checkpointer for interrupt() support ──
    checkpointer = _get_checkpointer()
    return workflow.compile(checkpointer=checkpointer)


# Lazy-initialized graph singleton — avoids connecting to PostgreSQL at import time
_story_graph = None


def get_story_graph():
    """Get or create the compiled story graph (lazy singleton)."""
    global _story_graph
    if _story_graph is None:
        _story_graph = create_story_graph()
    return _story_graph


async def run_story_generation(initial_state: StoryState, thread_id: str = None) -> StoryState:
    """
    Invoke the compiled story graph asynchronously.

    Args:
        initial_state: The initial state dict for the workflow
        thread_id: Unique thread ID for checkpointing (defaults to job_id).
                   Required for interrupt()/resume to work correctly.
    """
    graph = get_story_graph()
    tid = thread_id or initial_state.get("job_id", "unknown")
    config = {"configurable": {"thread_id": tid}}
    return await graph.ainvoke(initial_state, config=config)
