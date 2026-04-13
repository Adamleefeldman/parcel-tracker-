"""
Rate limiting via slowapi.

Rate limits are enforced per-IP.  Behind a reverse proxy (Cloudflare, nginx,
etc.) the real client IP arrives in the `X-Forwarded-For` header. Trusting
that header blindly is a spoofing vector — the `get_remote_address` function
below only honours it when all of the following are true:

    1. APP_ENV == "production"
    2. TRUSTED_PROXIES is set (comma-separated IPs or CIDRs)
    3. The *direct* peer IP (request.client.host) matches one of those proxies

If those conditions aren't met the function falls back to `request.client.host`
(the direct socket peer), which is the correct behaviour in local dev or when
no proxy is configured.

Usage
-----
Apply per-route with the ``@limiter.limit(...)`` decorator:

    from app.middleware.rate_limit import limiter

    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(request: Request, ...):
        ...

Global default limits are set here via ``default_limits`` so every route
has a sane backstop even without an explicit decorator.
"""

from __future__ import annotations

import logging

from fastapi import Request, status
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.network import get_client_ip

logger = logging.getLogger("parceltrack.api")


def get_remote_address(request: Request) -> str:
    """
    Determine the client IP for rate-limiting purposes.

    Delegates to the shared get_client_ip utility which honours
    X-Forwarded-For only in production behind a trusted proxy.
    Falls back to "127.0.0.1" if the peer address is unavailable.
    """
    settings = get_settings()
    return get_client_ip(request, settings.is_production, settings.TRUSTED_PROXIES) or "127.0.0.1"


# ── Limiter instance ──────────────────────────────────────────────────────────
#
# Rate limiting is disabled when APP_ENV == "testing" so the test suite can
# fire hundreds of requests without hitting limits. The limits only apply
# in development and production.

_settings = get_settings()
_enabled = _settings.APP_ENV not in ("testing",)

# Use Redis-backed storage so counters are shared across all API instances.
# Falls back to in-memory if Redis is unavailable (e.g. local dev without Redis).
_storage_uri = "memory://"
if _enabled:
    try:
        import redis as _redis_sync

        _redis_sync.from_url(_settings.REDIS_URL).ping()
        _storage_uri = _settings.REDIS_URL
    except Exception:
        logger.warning("Redis unavailable for rate limiting — falling back to in-memory store")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    storage_uri=_storage_uri,
    enabled=_enabled,
)


# ── Custom 429 response ──────────────────────────────────────────────────────


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a JSON 429 with a Retry-After header."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Rate limit exceeded. Slow down.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )
