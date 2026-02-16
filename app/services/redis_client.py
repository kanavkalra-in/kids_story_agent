"""
Shared Redis client — single connection pool reused across API and Celery workers.
Lazy-initialized to avoid connection errors when modules are imported in contexts
that don't need Redis.
"""
import redis
from app.config import settings
from typing import Optional

_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """
    Get or create the shared Redis client.
    Lazily initialized on first call.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url)
    return _redis_client
