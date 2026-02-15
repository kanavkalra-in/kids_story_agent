"""
LangGraph workflow for story generation.

Parallelism strategy (all handled natively by LangGraph — no asyncio.gather):

1. **Prompter parallelism** — Static edges: ``story_writer`` has edges to
   both ``image_prompter`` and ``video_prompter``; LangGraph runs them in
   parallel and waits for both before proceeding.

2. **Generator fan-out** — Dynamic ``Send``: Both prompters route to generators
   by inspecting the prompt lists and emitting one ``Send`` per image/video prompt.
   Each ``Send`` targets the corresponding generator node with the specific prompt,
   index and description embedded in the state dict.  Results accumulate via
   ``operator.add`` reducers on the ``*_urls`` / ``*_metadata`` state fields.

Graph shape:

    story_writer
        ├──► image_prompter ──┐
        └──► video_prompter ──┤
                              ▼ (fan-in)
        ┌──► generate_single_image (×N) ──┐
        └──► generate_single_video (×M) ──┤
                                          ▼
                                      assembler ──► END
"""

from langgraph.graph import StateGraph, END
from langgraph.types import Send
from app.agents.state import StoryState
from app.agents.story_writer import story_writer_node
from app.agents.image_prompter import image_prompter_node
from app.agents.video_prompter import video_prompter_node
from app.agents.image_generator import image_generator_node
from app.agents.video_generator import video_generator_node
from app.agents.assembler import assembler_node
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


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def create_story_graph() -> StateGraph:
    """Build and compile the LangGraph workflow."""

    workflow = StateGraph(StoryState)

    # -- Nodes --
    workflow.add_node("story_writer", story_writer_node)
    workflow.add_node("image_prompter", image_prompter_node)
    workflow.add_node("video_prompter", video_prompter_node)
    workflow.add_node("generate_single_image", image_generator_node)
    workflow.add_node("generate_single_video", video_generator_node)
    workflow.add_node("assembler", assembler_node)

    # -- Edges --

    # Entry
    workflow.set_entry_point("story_writer")

    # story_writer → both prompters (static edges, always run in parallel)
    workflow.add_edge("story_writer", "image_prompter")
    workflow.add_edge("story_writer", "video_prompter")

    # Both prompters → fan-in and route to generators
    # LangGraph handles fan-in automatically when both edges target the same conditional
    workflow.add_conditional_edges("image_prompter", route_to_generators,
                                  ["generate_single_image",
                                   "generate_single_video",
                                   "assembler"])
    workflow.add_conditional_edges("video_prompter", route_to_generators,
                                  ["generate_single_image",
                                   "generate_single_video",
                                   "assembler"])

    # All generators → assembler (fan-in: waits for every Send to complete)
    workflow.add_edge("generate_single_image", "assembler")
    workflow.add_edge("generate_single_video", "assembler")

    # assembler → end
    workflow.add_edge("assembler", END)

    return workflow.compile()


# Compiled graph singleton
story_graph = create_story_graph()


async def run_story_generation(initial_state: StoryState) -> StoryState:
    """Invoke the compiled story graph asynchronously."""
    return await story_graph.ainvoke(initial_state)
