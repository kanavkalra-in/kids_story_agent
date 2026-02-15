"""
URL resolution utilities for converting local storage paths to API URLs.
"""
from typing import Literal


def convert_local_path_to_url(
    file_path: str,
    media_type: Literal["image", "video"],
    api_base_url: str | None = None
) -> str:
    """
    Convert a local file path to an API URL.
    
    Args:
        file_path: Local storage path (e.g., "storage/images/stories/...")
        media_type: "image" or "video"
        api_base_url: Optional base URL for absolute URLs. If None, returns relative path.
        
    Returns:
        API URL (absolute if api_base_url provided, relative otherwise)
    """
    # If it's already a URL, return as-is
    if file_path.startswith(("http://", "https://")):
        return file_path
    
    # Determine the API endpoint prefix
    endpoint_prefix = f"/api/v1/stories/{media_type}s"
    
    # Handle storage paths
    if file_path.startswith(f"storage/{media_type}s/"):
        relative_path = file_path.replace(f"storage/{media_type}s/", "")
        relative_url = f"{endpoint_prefix}/{relative_path}"
    elif file_path.startswith("/"):
        # Already a relative URL path
        relative_url = file_path
    elif f"{media_type}s/" in file_path or "stories/" in file_path:
        # Handle partial paths like "stories/{story_id}/{file_id}.png"
        if f"stories/" in file_path:
            # Extract everything after "stories/"
            parts = file_path.split("stories/", 1)
            if len(parts) == 2:
                relative_url = f"{endpoint_prefix}/stories/{parts[1]}"
            else:
                relative_url = f"{endpoint_prefix}/{file_path}"
        else:
            relative_url = f"{endpoint_prefix}/{file_path}"
    else:
        # Assume it's a relative path that needs the endpoint prefix
        relative_url = f"{endpoint_prefix}/{file_path}"
    
    # Return absolute URL if base URL provided, otherwise relative
    if api_base_url:
        return f"{api_base_url.rstrip('/')}{relative_url}"
    return relative_url
