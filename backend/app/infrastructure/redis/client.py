from __future__ import annotations

import redis.asyncio as redis

from app.config import settings

_pool: redis.ConnectionPool | None = None


def get_redis_client() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return redis.Redis(connection_pool=_pool)
