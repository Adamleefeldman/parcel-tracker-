"""
Redis connection module.

Provides a single async Redis client shared across the application.
Used for: JWT access token revocation, rate limiting, future caching.
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url

from app.core.config import get_settings

logger = logging.getLogger("parceltrack.api")

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return the shared Redis client, initialising it on first call."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis_from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def get_redis() -> Redis:
    """FastAPI dependency — yields the shared Redis client."""
    return get_redis_client()


# ── JWT deny-list ─────────────────────────────────────────────────────────────
#
# On logout we store the token's jti (JWT ID) in Redis with a TTL equal to
# the token's remaining lifetime. Any subsequent request carrying that token
# is rejected even though the signature is still valid.

_JTI_PREFIX = "revoked_jti:"


async def revoke_access_token(jti: str, ttl_seconds: int) -> None:
    """Mark a JWT access token as revoked. ttl_seconds should be the token's remaining lifetime."""
    redis = get_redis_client()
    await redis.setex(f"{_JTI_PREFIX}{jti}", ttl_seconds, "1")


async def is_token_revoked(jti: str) -> bool:
    """Return True if the given jti has been revoked."""
    redis = get_redis_client()
    return await redis.exists(f"{_JTI_PREFIX}{jti}") == 1
