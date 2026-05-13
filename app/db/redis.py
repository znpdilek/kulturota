"""
Redis İstemcisi
================
PRD §18.1 — Rate limiting, LLM decision cache, hot key cache.

Tek bir global ``redis.Redis`` istemcisi kullanılır; FastAPI dependency
katmanı (``app.api.deps.get_redis``) bu istemciyi yield eder.
"""

from __future__ import annotations

from functools import lru_cache

import redis

from app.core.config import settings


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    """Tek-instance Redis client. Bağlantı havuzu otomatiktir."""
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
        health_check_interval=30,
    )
