"""
LangGraph workflow for story generation with evaluation, guardrails,
and human-in-the-loop review.

Parallelism strategy (all handled natively by LangGraph — no asyncio.gather):

1. **Prompter parallelism** — Static edges: ``story_writer`` has edges to
   both ``image_prompter`` and ``video_prompter``; LangGraph runs them in
   parallel and waits for both before proceeding.

2. **Generator fan-out** — Dynamic ``Send``: Both prompters route to generators
   by inspecting the prompt lists and emitting one ``Send`` per image/video prompt.

3. **Guardrail fan-out** — From the assembler, ``route_to_guardrails`` emits
   one ``Send`` per: story_evaluator, story_guardrail, each image_guardrail,
   each video_guardrail. All run in parallel.

4. **Human-in-the-loop** — ``human_review_gate`` uses LangGraph's ``interrupt()``
   to pause execution. State is checkpointed to PostgresSaver. The graph resumes
   when the review API calls ``Command(resume=...)``.

Graph shape:

    story_writer
        ├──► image_prompter ──┐
        └──► video_prompter ──┤
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
           mark_auto_rejected         human_review_gate (interrupt)
                    │                         │
                   END              ┌── decision? ──┐
                                    │               │
                              [approved]       [rejected]
                                    │               │
                               publisher      mark_rejected
                                    │               │
                                   END             END
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


def route_to_generators(state: StoryState) -> Union[list[Send], str]:
    """
    Fan-out from prompters to individual generator instances.

    Creates one ``Send`` per image prompt and one per video prompt.  Each
    ``Send`` only includes the minimal state keys needed by the generator nodes
    to avoid copying the full state (including story text and all prompts).
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
        # Nothing to generate → go straight to assembler
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
    Falls back to MemorySaver for development/testing.
    """
    conn_string = settings.checkpointer_conn_string

    if not conn_string:
        # Derive sync connection string from async database_url
        # asyncpg → psycopg2 for the checkpointer
        conn_string = settings.database_url.replace(
            "postgresql+asyncpg://", "postgresql://"
        )

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        checkpointer = PostgresSaver.from_conn_string(conn_string)
        checkpointer.setup()
        logger.info("Using PostgresSaver checkpointer for human-in-the-loop support")
        return checkpointer
    except Exception as e:
        logger.warning(
            f"Failed to create PostgresSaver checkpointer: {e}. "
            f"Falling back to MemorySaver (not suitable for production)."
        )
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()


def create_story_graph() -> StateGraph:
    """Build and compile the LangGraph workflow with evaluation, guardrails, and HITL."""

    workflow = StateGraph(StoryState)

    # ── Generation nodes (existing) ──
    workflow.add_node("story_writer", story_writer_node)
    workflow.add_node("image_prompter", image_prompter_node)
    workflow.add_node("video_prompter", video_prompter_node)
    workflow.add_node("generate_single_image", image_generator_node)
    workflow.add_node("generate_single_video", video_generator_node)
    workflow.add_node("assembler", assembler_node)

    # ── Evaluation & Guardrail nodes (NEW) ──
    workflow.add_node("story_evaluator", story_evaluator_node)
    workflow.add_node("story_guardrail", story_guardrail_node)
    workflow.add_node("image_guardrail_with_retry", image_guardrail_with_retry_node)
    workflow.add_node("video_guardrail_with_retry", video_guardrail_with_retry_node)
    workflow.add_node("guardrail_aggregator", guardrail_aggregator_node)

    # ── Human review & publish nodes (NEW) ──
    workflow.add_node("human_review_gate", human_review_gate_node)
    workflow.add_node("publisher", publisher_node)
    workflow.add_node("mark_auto_rejected", mark_auto_rejected_node)
    workflow.add_node("mark_rejected", mark_rejected_node)

    # ── Edges: Generation pipeline (existing) ──
    workflow.set_entry_point("story_writer")

    # story_writer → both prompters (static edges, always run in parallel)
    workflow.add_edge("story_writer", "image_prompter")
    workflow.add_edge("story_writer", "video_prompter")

    # Both prompters → fan-in and route to generators
    workflow.add_conditional_edges("image_prompter", route_to_generators,
                                  ["generate_single_image",
                                   "generate_single_video",
                                   "assembler"])
    workflow.add_conditional_edges("video_prompter", route_to_generators,
                                  ["generate_single_image",
                                   "generate_single_video",
                                   "assembler"])

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


# Compiled graph singleton
story_graph = create_story_graph()


async def run_story_generation(initial_state: StoryState, thread_id: str = None) -> StoryState:
    """
    Invoke the compiled story graph asynchronously.

    Args:
        initial_state: The initial state dict for the workflow
        thread_id: Unique thread ID for checkpointing (defaults to job_id).
                   Required for interrupt()/resume to work correctly.
    """
    tid = thread_id or initial_state.get("job_id", "unknown")
    config = {"configurable": {"thread_id": tid}}
    return await story_graph.ainvoke(initial_state, config=config)
