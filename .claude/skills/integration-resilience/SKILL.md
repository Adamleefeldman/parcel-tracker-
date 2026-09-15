---
name: integration-resilience
description: Use whenever code calls a third-party HTTP API — payment gateways, push notification providers (Expo, FCM, APNS), maps/geocoding, AIS/vessel data, email (SendGrid, Postmark), SMS (Twilio), AI providers, scraping endpoints, or any outbound integration that can time out, 5xx, rate-limit, or briefly disappear. Triggers on phrases like "call the X API", "third-party flaky", "retry logic", "circuit breaker", "exponential backoff", "Retry-After", "httpx client", "external service is slow", "we keep hammering them when they're down", or when you see a `requests.post(...)` / `httpx.get(...)` with no timeout, no retry, and no breaker. Also triggers on the inverse: a tangle of bespoke retry loops, each slightly different, in five different services.
---

# Resilient outbound HTTP — one helper for all providers

When a backend calls more than one outbound provider (and most of them do), each provider deserves the *same* resilience treatment: timeout, jittered backoff retry on transient errors, a circuit breaker that prevents thundering-herd retries when the provider is in a bad state, typed exceptions so callers can distinguish "retry me" from "give up." Most codebases re-implement this per integration, badly. The point of this skill is: write it once, use it everywhere.

## The shape

Two functions and a small exception hierarchy.

### `build_client(provider) -> httpx.AsyncClient`

A factory that returns an `httpx.AsyncClient` with provider-aware defaults: total timeout from config, `User-Agent: <app>/<version> (<provider>)`, an injectable `transport` parameter for tests.

### `request(provider, client, method, url, **kwargs) -> httpx.Response`

The actual call site. Wraps a single HTTP request with:

- A check against the provider's circuit-breaker state in Redis.
- Jittered exponential backoff retry on transient failures (timeouts, 5xx, network errors).
- Status-code-aware exception mapping (401/403 → auth error; 429 → rate limited; 5xx → unavailable; other 4xx → caller's problem, return the response).
- `Retry-After` header parsing on 429.

### Typed exception hierarchy

```python
class IntegrationError(Exception):
    def __init__(self, msg: str, *, provider: str): ...

class IntegrationTimeout(IntegrationError): ...      # retry me
class IntegrationUnavailable(IntegrationError): ...  # retry me
class IntegrationRateLimited(IntegrationError):      # caller decides
    retry_after_seconds: float | None
class IntegrationAuthError(IntegrationError): ...    # do NOT retry
```

Callers branch on the type to decide retry-vs-drop. A Celery task wrapping a provider call catches `IntegrationTimeout | IntegrationUnavailable | IntegrationRateLimited` to retry with backoff; it catches `IntegrationAuthError` to log and drop (retrying won't fix a bad key).

## Circuit breaker — concurrency model

The breaker has three states (closed → open → half-open) but only two pieces of Redis state:

| Key | Type | Purpose |
|---|---|---|
| `integrations:cb:<provider>:failures` | counter | Increments on every transient failure. No TTL — a slow drip of failures still trips eventually. |
| `integrations:cb:<provider>:open` | flag with TTL | Set when failures cross the threshold. TTL is the cooldown. While the key exists, the breaker is open. When it expires, the next caller is a half-open probe. |

The TTL on the `open` key *is* the half-open transition. No explicit state machine, no race window: when the key is gone, the next request goes through; if it succeeds, `_record_success` deletes the counter and the breaker is fully closed; if it fails, `_record_failure` re-opens the flag.

### Why this concurrency model is non-obvious

- **INCR is atomic** — exactly one caller observes `failures == threshold`. That's the caller that logs "breaker opened".
- **SETEX is idempotent** — every caller that sees `failures >= threshold` issues the same `SETEX integrations:cb:<provider>:open <cooldown> "1"`. They all converge on the same end state. No "check, then set" race window.
- **The counter is NOT reset on trip.** Resetting it from one caller while another concurrent caller is still incrementing is the original TOCTOU bug. Only `_record_success` (a success observation, which by definition isn't racing with concurrent failures on the same provider call) resets the counter.

These three rules are the only thing that keeps the breaker honest under concurrency. Don't optimize around them.

## Canonical template

```python
# app/integrations/_http.py

import random
import httpx
from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.integrations._exceptions import (
    IntegrationAuthError, IntegrationRateLimited,
    IntegrationTimeout, IntegrationUnavailable,
)

_CB_KEY_PREFIX = "integrations:cb:"

def _cb_open_key(provider: str) -> str:
    return f"{_CB_KEY_PREFIX}{provider}:open"

def _cb_failures_key(provider: str) -> str:
    return f"{_CB_KEY_PREFIX}{provider}:failures"


def build_client(provider: str, *, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.INTEGRATION_HTTP_TIMEOUT_SECONDS),
        headers={"User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION} ({provider})"},
        transport=transport,
    )


async def _is_circuit_open(provider: str) -> bool:
    return (await get_redis_client().exists(_cb_open_key(provider))) == 1


async def _record_failure(provider: str) -> bool:
    """Returns True if the breaker is open as of this call."""
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
            logger.warning("circuit_breaker_opened",
                           extra={"provider": provider})
        return True
    return False


async def _record_success(provider: str) -> None:
    await get_redis_client().delete(_cb_failures_key(provider))


def _backoff_seconds(attempt: int, *, base: float = 0.25, cap: float = 5.0) -> float:
    return min(base * (2**attempt) + random.uniform(0, base), cap)


async def request(provider: str, client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    if await _is_circuit_open(provider):
        raise IntegrationUnavailable(f"circuit open for {provider!r}", provider=provider)

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
                await _sleep(_backoff_seconds(attempt)); continue
            raise IntegrationTimeout(f"{provider} timed out", provider=provider) from exc
        except httpx.HTTPError as exc:
            last_exc = exc
            tripped = await _record_failure(provider)
            if not tripped and attempt + 1 < max_attempts:
                await _sleep(_backoff_seconds(attempt)); continue
            raise IntegrationUnavailable(f"{provider} network error: {exc}", provider=provider) from exc

        s = response.status_code
        if s < 400:
            await _record_success(provider)
            return response

        if s == 429:
            # Don't retry — the caller decides. Don't count against the breaker —
            # rate-limiting is a normal signal, not brokenness.
            raise IntegrationRateLimited(
                f"{provider} rate limited", provider=provider,
                retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
            )

        if s in (401, 403):
            # Auth failures won't get better by retrying and shouldn't count
            # against the breaker — they indicate *our* credentials, not their health.
            raise IntegrationAuthError(f"{provider} auth error ({s})", provider=provider)

        if 500 <= s < 600:
            tripped = await _record_failure(provider)
            if not tripped and attempt + 1 < max_attempts:
                await _sleep(_backoff_seconds(attempt)); continue
            raise IntegrationUnavailable(f"{provider} returned {s}", provider=provider)

        # 4xx other than 401/403/429 — caller's problem. Return the response.
        await _record_success(provider)
        return response

    raise IntegrationUnavailable(f"{provider} unreachable", provider=provider) from last_exc


async def _sleep(seconds: float) -> None:
    """Indirection so tests can monkey-patch sleep to a no-op."""
    import asyncio
    await asyncio.sleep(seconds)
```

## Design rules — and why they matter

### Rule 1: Per-provider breakers, not a global breaker

If Expo is down, that's no reason to stop calling Stripe. Namespace the Redis keys by provider so each external dependency has its own circuit.

### Rule 2: 401 / 403 / 429 do NOT count toward the breaker

These are normal provider signals:

- **401/403** means *your* credentials are wrong. Retrying won't fix it. Tripping the breaker on auth errors would mean a misconfigured key shuts you out of the provider until cooldown.
- **429** means you're sending too fast. Back off on the caller side. Counting it against the breaker on top would compound the slowdown.

Only count timeouts, network errors, and 5xx as breaker failures — those are *their* problem.

### Rule 3: Jitter, not pure exponential backoff

Pure `2**attempt` retry timing causes synchronized retries from many clients ("thundering herd"). Add `random.uniform(0, base)` so retries spread out. Cap at a sensible ceiling (e.g. 5s) so a long retry tail doesn't blow up your request budget.

### Rule 4: Retries at the request level, not at the httpx transport

You *can* put retries in a custom transport (`httpx-retries`, `tenacity` wrapped around the client). Don't. The advantages of request-level retries:

- The retry loop is directly testable with `httpx.MockTransport` — each retry counts as one transport call, so assertions are simple.
- You can skip retries when the breaker is open without any transport-level trickery.
- The retry policy is visible in one function, not split between a transport class and the call site.

### Rule 5: Typed exceptions are the API

Callers should `except IntegrationTimeout | IntegrationUnavailable` to know what's retryable. Raising a generic `Exception` or letting `httpx.HTTPError` leak past forces every caller to re-classify the same things.

### Rule 6: Celery wrappers retry only `IntegrationTimeout | IntegrationUnavailable | IntegrationRateLimited`

Permanent failures (`IntegrationAuthError`, 4xx for bad request, `DeviceNotRegistered` on Expo push) should *not* retry. Retrying a permanent failure means N times the log noise and zero recoveries. The Celery task body should look like:

```python
try:
    asyncio.run(_run())
except (IntegrationTimeout, IntegrationUnavailable, IntegrationRateLimited) as exc:
    raise self.retry(exc=exc, countdown=2**self.request.retries) from exc
except IntegrationError:
    logger.warning("permanent failure", exc_info=True)
    # drop
```

### Rule 7: Inject the transport for tests

`build_client(provider, transport=...)` lets tests pass `httpx.MockTransport` with a handler that returns crafted responses. Don't mock `httpx.AsyncClient.request`; tests should exercise the real request → retry → breaker path.

### Rule 8: Config knobs in one place

`INTEGRATION_HTTP_TIMEOUT_SECONDS`, `INTEGRATION_HTTP_RETRIES`, `INTEGRATION_CIRCUIT_BREAKER_THRESHOLD`, `INTEGRATION_CIRCUIT_BREAKER_COOLDOWN_SECONDS`. Don't pass these as function arguments — once you start, every caller gets a chance to be slightly wrong.

### Rule 9: Don't add bespoke per-provider retry logic on top

If Expo needs longer timeouts, *raise the global timeout*; the cost of a longer wait is paid only when something is wrong. If a provider needs special handling (chunked uploads, custom auth dance), put the special handling in the provider's wrapper module — but the underlying HTTP call still goes through `request()`. The exceptions and breaker behavior must remain uniform.

### Rule 10: The 4xx-other-than-401/403/429 case returns the response, not an exception

A `400 Bad Request` from a provider is a logical-level error (you sent bad data), not a resilience-level problem. Let the caller inspect the body and decide. Raising on every 4xx tempts callers to catch `Exception` broadly, which hides the actual error.

## When to skip this pattern

- **One-off scripts** — `httpx.get(url, timeout=10)` is fine for a CSV importer that runs once a quarter. Don't drag in Redis just to fetch a file.
- **Server-to-server calls inside your own VPC** — your own services should *not* need a circuit breaker layered on top of internal load balancing and retries. If you're doing this, fix the upstream service.
- **Streaming endpoints** — long-lived SSE/WebSocket connections need different resilience (heartbeat, reconnect with backoff). This helper is for unit requests.

## Reviewing a PR that touches an integration

- [ ] Is there a new `httpx.AsyncClient(...)` instantiated outside `build_client`? If yes, route it through `build_client`.
- [ ] Is there a bare `requests.*` / `httpx.*` call without a timeout? Reject it.
- [ ] Are 401/403/429 counted as breaker failures? If yes, fix.
- [ ] Does the Celery task retry on `IntegrationAuthError`? If yes, fix.
- [ ] Are tests using `httpx.MockTransport` against `request()`, not mocking the function itself?
- [ ] Are the breaker Redis keys namespaced per provider?
- [ ] Is there a new global timeout / retry tunable being passed as a function argument? Push back; it belongs in config.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| One slow provider causes alert flood for unrelated callers | Breaker is global, not per-provider |
| Bad API key locks the app out for the cooldown | 401/403 is being counted against the breaker |
| Retries amplify a 429 storm | 429 is being retried; it should raise immediately |
| Tests are slow because real backoffs run | `_sleep` indirection not monkey-patched in tests |
| Same minute every hour, every API instance hits a remote 429 in lockstep | No jitter in backoff timing |
| "Breaker is open" log appears once per second forever | The "log only at trip moment" guard is missing; only log when `failures == threshold` |

## Companion skills

- **`production-config-validation`** — for the integration-tunable settings (`INTEGRATION_HTTP_TIMEOUT_SECONDS`, etc.).
- **`fastapi-middleware-stack`** — for the request-id contextvar that should appear in every integration log line.
