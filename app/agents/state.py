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
