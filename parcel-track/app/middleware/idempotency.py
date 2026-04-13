"""
Idempotency key support for critical mutation endpoints.

Clients include an `Idempotency-Key` header (any unique string, typically a UUID)
on POST requests for payment and invoice creation. On the first request with a
given key we process normally and cache the response in Redis for 24 hours.
On any subsequent request with the same key we return the cached response
immediately without re-executing the handler — safe for network retries.

Usage (FastAPI dependency):

    @router.post("/payments")
    async def add_payment(
        idempotency: IdempotencyResult = Depends(require_idempotency),
        ...
    ):
        if idempotency.cached_response:
            return idempotency.cached_response

        result = ...  # do the work

        await idempotency.store(result)
        return result
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import Header, HTTPException, Request, status

from app.core.redis import get_redis

logger = logging.getLogger("parceltrack.api")

_IDEMPOTENCY_TTL = 86400  # 24 hours
_KEY_PREFIX = "idempotency:"


@dataclass
class IdempotencyResult:
    """Carries cached response (if any) and a callback to persist the new response."""

    key: str
    cached_response: Any | None = None
    _request: Request = field(repr=False, default=None)

    async def store(self, response_body: Any) -> None:
        """Persist the response so subsequent duplicate requests return it."""
        from app.core.redis import get_redis_client

        redis = get_redis_client()
        try:
            await redis.setex(
                f"{_KEY_PREFIX}{self.key}",
                _IDEMPOTENCY_TTL,
                json.dumps(response_body, default=str),
            )
        except Exception:
            logger.warning(
                "Failed to store idempotency response for key=%s", self.key, exc_info=True
            )


async def require_idempotency(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IdempotencyResult:
    """
    FastAPI dependency — requires an Idempotency-Key header.

    Returns an IdempotencyResult. If the key matches a cached response,
    `cached_response` is populated and the caller should return it immediately.
    """
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required for this endpoint.",
        )

    redis = await get_redis()
    redis_key = f"{_KEY_PREFIX}{idempotency_key}"

    try:
        cached = await redis.get(redis_key)
    except Exception:
        logger.warning("Redis unavailable for idempotency check — proceeding without cache")
        cached = None

    if cached:
        logger.info("Returning cached response for idempotency key=%s", idempotency_key)
        try:
            return IdempotencyResult(key=idempotency_key, cached_response=json.loads(cached))
        except json.JSONDecodeError:
            pass  # corrupted cache — re-process

    return IdempotencyResult(key=idempotency_key, _request=request)
