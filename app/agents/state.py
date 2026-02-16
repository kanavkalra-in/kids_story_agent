from typing import TypedDict, List, Optional, Annotated
import operator


class StoryState(TypedDict):
    """State for the story generation workflow.

    Fields annotated with ``operator.add`` are *reducer* fields — multiple
    parallel LangGraph ``Send`` instances each contribute a partial list,
    and the framework concatenates them automatically.
    """

    job_id: str
    prompt: str
    age_group: str
    num_illustrations: int
    webhook_url: Optional[str]
    generate_images: bool
    generate_videos: bool

    # Story generation (set by story_writer node)
    story_text: Optional[str]
    story_title: Optional[str]

    # Prompter outputs (set once per prompter, no reducer needed)
    image_prompts: List[str]
    image_descriptions: List[str]   # scene descriptions from image prompter
    video_prompts: List[str]
    video_descriptions: List[str]   # scene descriptions from video prompter

    # Generator outputs — accumulated from parallel Send instances via reducer
    image_urls: Annotated[List[str], operator.add]
    image_metadata: Annotated[List[dict], operator.add]
    video_urls: Annotated[List[str], operator.add]
    video_metadata: Annotated[List[dict], operator.add]

    # Runtime keys injected by routing function for generator nodes
    _current_prompt: Optional[str]
    _current_index: Optional[int]
    _current_description: Optional[str]

    # Error handling
    error: Optional[str]

    # ── Input Moderation (set by input_moderator node) ──
    input_moderation_passed: Optional[bool]

    # ── Evaluation Scores (set by story_evaluator node) ──
    evaluation_scores: Optional[dict]

    # ── Guardrail Results (reducer — each parallel Send appends violations) ──
    guardrail_violations: Annotated[List[dict], operator.add]

    # ── Aggregated guardrail outcome (set by guardrail_aggregator) ──
    guardrail_passed: Optional[bool]
    guardrail_summary: Optional[str]

    # ── Final media URLs after guardrail retries (reducer) ──
    # Each guardrail node returns the final good URL for its media item
    # Format: [{"index": 0, "url": "..."}, ...]
    image_urls_final: Annotated[List[dict], operator.add]
    video_urls_final: Annotated[List[dict], operator.add]

    # ── Human Review (set after interrupt resumes) ──
    review_decision: Optional[str]    # "approved" | "rejected"
    review_comment: Optional[str]
    reviewer_id: Optional[str]

    # ── Guardrail routing keys (injected by Send for guardrail nodes) ──
    _guardrail_media_url: Optional[str]
    _guardrail_media_index: Optional[int]
    _guardrail_original_prompt: Optional[str]
