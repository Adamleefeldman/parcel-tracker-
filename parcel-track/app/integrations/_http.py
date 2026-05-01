"""Resilient HTTP client for outbound provider calls.

Single entry point for every integration (Expo push, Destin8, VesselFinder, …):

    client = build_client("expo")
    response = await request("expo", client, "POST", url, json=payload)

`build_client` produces a configured `httpx.AsyncClient`. `request` wraps a call
with:

- Redis-backed per-provider circuit breaker (closed → open → half-open)
- Jittered exponential backoff retries on transient failures (timeouts, 5xx)
- Non-2xx mapping to typed `IntegrationError` subclasses
- `Retry-After` propagation on 429

The breaker state lives in Redis under `integrations:cb:<provider>`; a failure
count in `integrations:cb:<provider>:failures` increments on every transient
failure and trips the breaker once it hits the threshold. `open` → `half-open`
happens implicitly via TTL expiry: once the cooldown key is gone, the next
caller is allowed through as a probe.

Design note: retries live at the request level rather than as an httpx
transport. This keeps the retry loop directly testable with `httpx.MockTransport`
(each retry counts as one transport call) and lets us skip retries entirely
when the breaker is open without any transport-level trickery.
"""

from __future__ import annotations

import logging
import random
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.integrations._exceptions import (
    IntegrationAuthError,
    IntegrationRateLimited,
    IntegrationTimeout,
    IntegrationUnavailable,
)

logger = logging.getLogger("parceltrack.integrations")

# Project version — used in the User-Agent header so providers can identify us.
# Kept in sync with pyproject.toml [project].version manually; low-churn field.
_VERSION = "0.1.0"

_CB_KEY_PREFIX = "integrations:cb:"


def _cb_open_key(provider: str) -> str:
    return f"{_CB_KEY_PREFIX}{provider}:open"


def _cb_failures_key(provider: str) -> str:
    return f"{_CB_KEY_PREFIX}{provider}:failures"


def build_client(
    provider: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """Build an `httpx.AsyncClient` preconfigured for `provider`.

    - Total timeout from `INTEGRATION_HTTP_TIMEOUT_SECONDS`
    - `User-Agent: parceltrack/<version> (<provider>)`
    - `transport` is an injection point for tests (`httpx.MockTransport`)
    """
    settings = get_settings()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.INTEGRATION_HTTP_TIMEOUT_SECONDS),
        headers={"User-Agent": f"parceltrack/{_VERSION} ({provider})"},
        transport=transport,
    )


async def _is_circuit_open(provider: str) -> bool:
    redis = get_redis_client()
    return await redis.exists(_cb_open_key(provider)) == 1


async def _record_failure(provider: str) -> bool:
    """Increment the failure counter; trip the breaker once it hits the threshold.

    Concurrency model:
      - INCR is atomic — exactly one caller observes ``failures == threshold``.
      - SETEX of the open key is idempotent — every caller seeing
        ``failures >= threshold`` issues the same write, converging on the
        same open state. No check-then-act window.
      - The counter is NOT reset on trip. Resetting it from one caller while
        another concurrent caller has already incremented it is the original
        TOCTOU. Counter is reset only by ``_record_success`` (a success
        observation, never racing with concurrent failures).

    The counter itself has no TTL — a provider that fails once a day forever
    would eventually trip, which is fine. ``_record_success`` clears it on
    any successful response.

    Returns True if the breaker is open as of this call.
    """
    settings = get_settings()
    redis = get_redis_client()
    failures = await redis.incr(_cb_failures_key(provider))
    if failures >= settings.INTEGRATION_CIRCUIT_BREAKER_THRESHOLD:
        await redis.setex(
            _cb_open_key(provider),
            settings.INTEGRATION_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
            "1",
        )
        if failures == settings.INTEGRATION_CIRCUIT_BREAKER_THRESHOLD:
            # Log only at the moment of crossing — not on every later observation.
            logger.warning(
                "circuit_breaker_opened",
                extra={
                    "provider": provider,
                    "cooldown_s": settings.INTEGRATION_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
                },
            )
        return True
    return False


async def _record_success(provider: str) -> None:
    redis = get_redis_client()
    await redis.delete(_cb_failures_key(provider))


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a `Retry-After` header. Supports the seconds form; ignores HTTP-date."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        # HTTP-date form is legal but none of our current providers emit it.
        return None


def _backoff_seconds(attempt: int, *, base: float = 0.25, cap: float = 5.0) -> float:
    """Jittered exponential backoff: base * 2**attempt + uniform(0, base)."""
    return min(base * (2**attempt) + random.uniform(0, base), cap)  # noqa: S311 — jitter, not crypto


async def request(
    provider: str,
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Make a request with retries, breaker, and typed error mapping.

    Raises:
        IntegrationUnavailable: circuit open, 5xx after retries, or network error
        IntegrationTimeout:     timeout after retries
        IntegrationRateLimited: 429 (not retried — caller chooses)
        IntegrationAuthError:   401 / 403
    """
    if await _is_circuit_open(provider):
        raise IntegrationUnavailable(f"circuit open for provider {provider!r}", provider=provider)

    settings = get_settings()
    max_attempts = settings.INTEGRATION_HTTP_RETRIES + 1
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            last_exc = exc
            tripped = await _record_failure(provider)
            if not tripped and attempt + 1 < max_attempts:
                await _sleep(_backoff_seconds(attempt))
                continue
            raise IntegrationTimeout(f"{provider} timed out", provider=provider) from exc
        except httpx.HTTPError as exc:
            last_exc = exc
            tripped = await _record_failure(provider)
            if not tripped and attempt + 1 < max_attempts:
                await _sleep(_backoff_seconds(attempt))
                continue
            raise IntegrationUnavailable(
                f"{provider} network error: {exc}", provider=provider
            ) from exc

        status = response.status_code
        if status < 400:
            await _record_success(provider)
            return response

        if status == 429:
            # Don't retry rate-limit responses — the caller decides whether to
            # back off and for how long. Don't count them against the breaker
            # either: rate-limiting is a normal provider signal, not brokenness.
            raise IntegrationRateLimited(
                f"{provider} rate limited",
                provider=provider,
                retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
            )

        if status in (401, 403):
            # Auth failures won't get better by retrying and shouldn't count
            # against the breaker — they indicate our credentials, not their health.
            raise IntegrationAuthError(f"{provider} auth error ({status})", provider=provider)

        if 500 <= status < 600:
            tripped = await _record_failure(provider)
            if not tripped and attempt + 1 < max_attempts:
                await _sleep(_backoff_seconds(attempt))
                continue
            raise IntegrationUnavailable(f"{provider} returned {status}", provider=provider)

        # 4xx other than 401/403/429 — caller's problem (bad request, not found, …).
        # Return the response so they can inspect the body.
        await _record_success(provider)
        return response

    # Defensive: loop should always raise or return above.
    raise IntegrationUnavailable(f"{provider} unreachable", provider=provider) from last_exc


async def _sleep(seconds: float) -> None:
    """Indirection so tests can monkey-patch sleep to a no-op."""
    import asyncio

    await asyncio.sleep(seconds)
