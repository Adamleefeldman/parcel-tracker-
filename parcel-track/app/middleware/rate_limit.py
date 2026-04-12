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

import ipaddress

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse

from app.core.config import get_settings


def _parse_trusted_proxies(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse a comma-separated list of IPs / CIDRs into network objects."""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            # Silently skip malformed entries — log a warning in P2 when we
            # have structured logging.
            pass
    return networks


def get_remote_address(request: Request) -> str:
    """
    Determine the client IP for rate-limiting purposes.

    Honours X-Forwarded-For only when running in production behind a
    known, trusted reverse proxy (identified via the TRUSTED_PROXIES env
    var).  In all other cases, falls back to the direct socket peer.
    """
    settings = get_settings()
    peer_ip = request.client.host if request.client else "127.0.0.1"

    if settings.is_production and settings.TRUSTED_PROXIES:
        trusted = _parse_trusted_proxies(settings.TRUSTED_PROXIES)
        try:
            peer = ipaddress.ip_address(peer_ip)
        except ValueError:
            return peer_ip

        if any(peer in network for network in trusted):
            # The direct connection comes from a trusted proxy — honour XFF.
            xff = request.headers.get("X-Forwarded-For", "")
            if xff:
                # XFF is a chain: "client, proxy1, proxy2". Take the leftmost
                # (original client) entry.
                return xff.split(",")[0].strip()

    return peer_ip


# ── Limiter instance ──────────────────────────────────────────────────────────
#
# Rate limiting is disabled when APP_ENV == "testing" so the test suite can
# fire hundreds of requests without hitting limits. The limits only apply
# in development and production.

_settings = get_settings()
_enabled = _settings.APP_ENV not in ("testing",)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    storage_uri="memory://",  # In-process store — good enough for P0.
    # P2: swap to Redis once we wire REDIS_URL for caching.
    enabled=_enabled,
)


# ── Custom 429 response ──────────────────────────────────────────────────────


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a JSON 429 with a Retry-After header."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Slow down.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )
