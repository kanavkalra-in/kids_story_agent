"""
Shared local storage utilities for saving images and videos.

Consolidates the _save_image_locally / _save_video_locally logic
previously duplicated across image_generator.py and image_guardrail.py
(and their video counterparts).
"""

from pathlib import Path

from app.config import settings


def save_image_locally(image_data: bytes, story_id: str, image_id: str) -> str:
    """Save an image to local storage and return the relative file path."""
    base_storage_path = Path(settings.local_storage_path)
    if not base_storage_path.is_absolute():
        base_storage_path = Path.cwd() / base_storage_path

    storage_dir = base_storage_path / "stories" / story_id
    storage_dir.mkdir(parents=True, exist_ok=True)

    image_path = storage_dir / f"{image_id}.png"
    with open(image_path, "wb") as f:
        f.write(image_data)

    return str(image_path.relative_to(Path.cwd()))


def save_video_locally(video_data: bytes, story_id: str, video_id: str) -> str:
    """Save a video to local storage and return the relative file path."""
    base_storage_path = Path(settings.local_video_storage_path)
    if not base_storage_path.is_absolute():
        base_storage_path = Path.cwd() / base_storage_path

    storage_dir = base_storage_path / "stories" / story_id
    storage_dir.mkdir(parents=True, exist_ok=True)

    video_path = storage_dir / f"{video_id}.mp4"
    with open(video_path, "wb") as f:
        f.write(video_data)

    return str(video_path.relative_to(Path.cwd()))
