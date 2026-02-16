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

    num_illustrations = state.get("num_illustrations", "NOT SET")
    logger.info(
        f"Job {job_id}: [ROUTE_IMAGE_GENERATORS] Found {len(image_prompts)} image prompt(s) in state. "
        f"num_illustrations={num_illustrations}, generate_images={generate_images}"
    )
    
    if len(image_prompts) != num_illustrations and isinstance(num_illustrations, int):
        logger.error(
            f"Job {job_id}: [ROUTE_IMAGE_GENERATORS] MISMATCH! Expected {num_illustrations} prompt(s) "
            f"but found {len(image_prompts)} prompt(s). This will cause {len(image_prompts)} image(s) to be generated!"
        )
    
    for i, prompt in enumerate(image_prompts):
        desc = image_descriptions[i] if i < len(image_descriptions) else ""
        sends.append(Send("generate_single_image", {
            "job_id": job_id,
            "generate_images": generate_images,
            "_current_prompt": prompt,
            "_current_index": i,
            "_current_description": desc,
        }))

    # If there are no prompts but generation is enabled, this is an error
    if not sends and generate_images:
        error_msg = (
            f"Job {job_id}: Image generation was enabled but image_prompter "
            f"returned no prompts. This indicates the prompter failed or returned empty results."
        )
        logger.error(error_msg)
        from app.agents.nodes.generation.prompter_utils import StoryGenerationError
        raise StoryGenerationError(error_msg)
    
    # If no sends and generation is disabled, create a no-op Send that immediately completes
    # This ensures assembler waits for all paths (including other generators) via fan-in
    # We can't route directly to assembler as it would cancel other active Send nodes
    if not sends:
        logger.info(f"Job {job_id}: No image prompts to generate (generation disabled), creating no-op")
        # Return empty list - LangGraph will handle this, but we need to ensure
        # assembler still waits. Actually, we should create a no-op generator.
        # For now, return empty list and let the graph handle it
        # The key is that assembler has edges from generators, so it will wait
        return []
    
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

    # If there are no prompts but generation is enabled, this is an error
    if not sends and generate_videos:
        error_msg = (
            f"Job {job_id}: Video generation was enabled but video_prompter "
            f"returned no prompts. This indicates the prompter failed or returned empty results."
        )
        logger.error(error_msg)
        from app.agents.nodes.generation.prompter_utils import StoryGenerationError
        raise StoryGenerationError(error_msg)
    
    # If no sends and generation is disabled, return empty list
    # This ensures we don't route directly to assembler (which would cancel other Send nodes)
    # Assembler will run when all generators complete via their edges
    if not sends:
        logger.info(f"Job {job_id}: No video prompts to generate (generation disabled), returning empty")
        return []
    
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
    image_urls = state.get("image_urls", [])
    num_illustrations = state.get("num_illustrations")
    
    logger.info(
        f"Job {job_id}: [ROUTE_GUARDRAILS] Found {len(image_urls)} image URL(s) in state, "
        f"num_illustrations={num_illustrations}, image_prompts count={len(image_prompts)}"
    )
    
    # CRITICAL FIX: Limit to expected count to prevent duplicate guardrail checks
    if num_illustrations is not None and len(image_urls) > num_illustrations:
        logger.warning(
            f"Job {job_id}: [ROUTE_GUARDRAILS] Found {len(image_urls)} image URL(s) but expected {num_illustrations}. "
            f"This indicates a bug - reducer field accumulation issue. Truncating to {num_illustrations}."
        )
        image_urls = image_urls[:num_illustrations]
    
    for i, url in enumerate(image_urls):
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

def _get_checkpointer_conn_string() -> str:
    """Return the PostgreSQL connection string for the checkpointer."""
    conn_string = settings.checkpointer_conn_string
    if not conn_string:
        conn_string = settings.database_url.replace(
            "postgresql+asyncpg://", "postgresql://"
        )
    return conn_string


def _build_workflow() -> StateGraph:
    """Build the LangGraph workflow structure (nodes + edges, no compilation)."""

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

    # Each prompter routes to generators via Send (for parallel execution)
    # When no prompts exist, routing returns empty list and prompter completes
    workflow.add_conditional_edges("image_prompter", route_to_image_generators,
                                  ["generate_single_image"])
    workflow.add_conditional_edges("video_prompter", route_to_video_generators,
                                  ["generate_single_video"])

    # All generators → assembler (fan-in)
    # LangGraph will wait for ALL incoming edges to assembler before running it
    # When prompters return empty Send lists, they complete but don't create edges
    # Assembler only runs when all active generators (via Send) complete
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

    return workflow


# Cached workflow structure — nodes and edges are event-loop-agnostic
_workflow: StateGraph | None = None


def get_workflow() -> StateGraph:
    """Get or create the workflow graph structure (lazy singleton)."""
    global _workflow
    if _workflow is None:
        _workflow = _build_workflow()
    return _workflow


async def run_story_generation(initial_state: StoryState, thread_id: str = None) -> StoryState:
    """
    Invoke the compiled story graph asynchronously.

    A fresh AsyncPostgresSaver is created per invocation so the connection
    is always bound to the current event loop (important for Celery workers
    that call asyncio.run() per task).

    Args:
        initial_state: The initial state dict for the workflow
        thread_id: Unique thread ID for checkpointing (defaults to job_id).
                   Required for interrupt()/resume to work correctly.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    workflow = get_workflow()
    tid = thread_id or initial_state.get("job_id", "unknown")
    config = {"configurable": {"thread_id": tid}}
    conn_string = _get_checkpointer_conn_string()

    async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:
        graph = workflow.compile(checkpointer=checkpointer)
        logger.info("Using AsyncPostgresSaver checkpointer for human-in-the-loop support")
        return await graph.ainvoke(initial_state, config=config)
