"""
Application-wide constants to replace magic numbers and strings.
"""
# Timeouts (in seconds)
HTTP_TIMEOUT = 30.0
HTTP_LONG_TIMEOUT = 60.0
VIDEO_POLL_INITIAL_INTERVAL = 3  # Start with 3 seconds
VIDEO_POLL_MAX_INTERVAL = 15  # Cap at 15 seconds
VIDEO_POLL_BACKOFF_MULTIPLIER = 1.5  # Multiply by this each attempt
VIDEO_MAX_POLL_ATTEMPTS = 60  # Maximum number of polling attempts

# Age groups
VALID_AGE_GROUPS = ["3-5", "6-8", "9-12"]
DEFAULT_AGE_GROUP = "6-8"

# Default values
DEFAULT_NUM_ILLUSTRATIONS = 3
MAX_NUM_ILLUSTRATIONS = 10
MIN_NUM_ILLUSTRATIONS = 1

# Story constraints
MAX_PROMPT_LENGTH_CHARS = 10000
DEFAULT_STORY_TITLE = "A Wonderful Story"

# File extensions
ALLOWED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
ALLOWED_VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mov')

# Redis cache TTL (in seconds)
JOB_STATUS_CACHE_TTL = 3600  # 1 hour
