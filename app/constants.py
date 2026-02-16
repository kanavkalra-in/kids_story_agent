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

# ── Guardrail Constants ──
# Image guardrail hard-fail categories (from OpenAI omni-moderation)
IMAGE_HARD_FAIL_CATEGORIES = frozenset({
    "sexual", "sexual/minors", "violence", "violence/graphic",
})

# PII regex patterns for fast text scanning
PII_PATTERNS = {
    "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "phone": r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
}

# Guardrail severity levels
SEVERITY_HARD = "hard"
SEVERITY_SOFT = "soft"

# Review decisions
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_AUTO_REJECTED = "auto_rejected"
REVIEW_TIMEOUT_REJECTED = "timeout_rejected"
