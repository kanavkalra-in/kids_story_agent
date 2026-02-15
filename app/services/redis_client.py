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


# Backward compatibility: maintain redis_client as a property that calls get_redis_client
# This allows existing code using redis_client directly to continue working
class _RedisClientProxy:
    """Proxy object that lazily initializes Redis client on attribute access."""
    def __getattr__(self, name):
        return getattr(get_redis_client(), name)


redis_client = _RedisClientProxy()
