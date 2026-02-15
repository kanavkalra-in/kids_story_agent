"""
Shared OpenAI client singleton to avoid creating a new client + connection pool per request.
"""
from openai import OpenAI
from app.config import settings
import logging

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    """
    Get or create the shared OpenAI client.
    Lazily initialized on first call so it won't fail at import time
    if the API key isn't configured.
    """
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured (OPENAI_API_KEY)")
        _client = OpenAI(api_key=settings.openai_api_key)
        logger.debug("Initialized shared OpenAI client")
    return _client
