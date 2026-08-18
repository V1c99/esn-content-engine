"""Caching search responses in Redis.

The same query gives the same answer until the library changes, and people retype the same
few briefs all day. If REDIS_URL is not set none of this runs and the search just recomputes.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import structlog

log = structlog.get_logger(__name__)


class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class NoCache:
    """What gets used when Redis is not configured."""

    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        return None


class RedisCache:
    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self._redis = Redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        try:
            # decode_responses is on, so this is a str, but the stub says bytes | str | None.
            value = await self._redis.get(key)
        except Exception as error:
            # A cache that is down must not take the search down with it.
            log.warning("cache_read_failed", error=str(error))
            return None
        return str(value) if value is not None else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self._redis.set(key, value, ex=ttl_seconds)
        except Exception as error:
            log.warning("cache_write_failed", error=str(error))

    async def close(self) -> None:
        await self._redis.aclose()


def build_cache(redis_url: str | None) -> Cache:
    if redis_url is None:
        return NoCache()
    return RedisCache(redis_url)


def key_for(query: str, limit: int) -> str:
    """The whole query decides the key, including the part that gets excluded.

    Hashing it keeps the key short and stops a long brief with punctuation in it from
    becoming an awkward Redis key.
    """
    digest = hashlib.sha256(f"{query}|{limit}".encode()).hexdigest()[:32]
    return f"search:{digest}"
