"""Unit tests for app/integrations/_http.py.

Uses httpx.MockTransport — zero real network. Uses fakeredis for the circuit
breaker so we assert on real Redis semantics (TTL, INCR, SETEX) instead of
mocking our own abstraction.
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "testing")

import httpx
import pytest

from app.integrations import _http
from app.integrations._exceptions import (
    IntegrationAuthError,
    IntegrationRateLimited,
    IntegrationTimeout,
    IntegrationUnavailable,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Retry backoff sleeps would make the suite slow and flaky; stub them out."""

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(_http, "_sleep", _instant)


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """Swap the shared Redis client for an in-process fakeredis instance.

    The circuit breaker uses INCR + SETEX; fakeredis implements both faithfully
    so tests exercise the same code path as production.
    """
    try:
        import fakeredis.aioredis as fakeredis_aio
    except ImportError:
        pytest.skip("fakeredis not installed — skipping breaker tests")

    client = fakeredis_aio.FakeRedis(decode_responses=True)
    monkeypatch.setattr(_http, "get_redis_client", lambda: client)
    yield client


def _transport_returning(*responses: httpx.Response) -> httpx.MockTransport:
    """Return a MockTransport that yields `responses` in order, then repeats the last."""
    it = iter(responses)
    last: httpx.Response | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal last
        try:
            last = next(it)
        except StopIteration:
            assert last is not None
        return last

    return httpx.MockTransport(handler)


def _transport_raising(*excs: Exception) -> httpx.MockTransport:
    it = iter(excs)

    def handler(request: httpx.Request) -> httpx.Response:
        raise next(it)

    return httpx.MockTransport(handler)


def _counting_transport(response: httpx.Response) -> tuple[httpx.MockTransport, list[int]]:
    """Transport that records how many times it was called."""
    counter = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        counter[0] += 1
        return response

    return httpx.MockTransport(handler), counter


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_successful_call_returns_response_and_clears_failures(_fake_redis):
    transport = _transport_returning(httpx.Response(200, json={"ok": True}))
    client = _http.build_client("testp", transport=transport)
    # Seed a prior failure to prove success wipes it.
    await _fake_redis.set(_http._cb_failures_key("testp"), "2")

    resp = await _http.request("testp", client, "GET", "https://example.test/x")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert await _fake_redis.exists(_http._cb_failures_key("testp")) == 0


async def test_retry_then_succeed():
    transport = _transport_returning(
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json={"ok": True}),
    )
    client = _http.build_client("testp", transport=transport)

    resp = await _http.request("testp", client, "GET", "https://example.test/x")

    assert resp.status_code == 200


async def test_retry_exhausted_raises_unavailable():
    # INTEGRATION_HTTP_RETRIES defaults to 2 → 3 attempts total.
    resp_503 = httpx.Response(503)
    transport, counter = _counting_transport(resp_503)
    client = _http.build_client("testp", transport=transport)

    with pytest.raises(IntegrationUnavailable):
        await _http.request("testp", client, "GET", "https://example.test/x")

    assert counter[0] == 3


async def test_timeout_after_retries_raises_timeout():
    transport = _transport_raising(
        httpx.ConnectTimeout("t1"),
        httpx.ConnectTimeout("t2"),
        httpx.ConnectTimeout("t3"),
    )
    client = _http.build_client("testp", transport=transport)

    with pytest.raises(IntegrationTimeout):
        await _http.request("testp", client, "GET", "https://example.test/x")


async def test_429_propagates_retry_after():
    transport = _transport_returning(
        httpx.Response(429, headers={"Retry-After": "42"}),
    )
    client = _http.build_client("testp", transport=transport)

    with pytest.raises(IntegrationRateLimited) as exc_info:
        await _http.request("testp", client, "GET", "https://example.test/x")

    assert exc_info.value.retry_after_seconds == 42


async def test_429_is_not_retried():
    transport, counter = _counting_transport(httpx.Response(429))
    client = _http.build_client("testp", transport=transport)

    with pytest.raises(IntegrationRateLimited):
        await _http.request("testp", client, "GET", "https://example.test/x")

    assert counter[0] == 1


async def test_auth_error_raised_for_401_and_403():
    for status in (401, 403):
        transport = _transport_returning(httpx.Response(status))
        client = _http.build_client("testp", transport=transport)
        with pytest.raises(IntegrationAuthError):
            await _http.request("testp", client, "GET", "https://example.test/x")


async def test_circuit_opens_after_threshold_failures(_fake_redis):
    # Threshold is 5; one request that 5xxs 3 times == 3 failures.
    # Drive failures by repeatedly exhausting retries.
    resp_503 = httpx.Response(503)
    transport, _ = _counting_transport(resp_503)
    client = _http.build_client("testp", transport=transport)

    # 5 failures worth — each call records 3 (retries_exhausted). We set the
    # counter directly so we only need one real request to flip the trip.
    await _fake_redis.set(_http._cb_failures_key("testp"), "4")

    with pytest.raises(IntegrationUnavailable):
        await _http.request("testp", client, "GET", "https://example.test/x")

    # After threshold hits: open key exists, failures counter is reset.
    assert await _fake_redis.exists(_http._cb_open_key("testp")) == 1
    assert await _fake_redis.exists(_http._cb_failures_key("testp")) == 0


async def test_open_circuit_short_circuits_without_transport_call(_fake_redis):
    # Manually open the breaker.
    await _fake_redis.setex(_http._cb_open_key("testp"), 60, "1")

    transport, counter = _counting_transport(httpx.Response(200))
    client = _http.build_client("testp", transport=transport)

    with pytest.raises(IntegrationUnavailable):
        await _http.request("testp", client, "GET", "https://example.test/x")

    assert counter[0] == 0, "open breaker must not call the provider"


async def test_malformed_json_is_caller_problem_not_http_error():
    """The helper does not parse JSON. A 200 with garbage body still returns a Response."""
    transport = _transport_returning(httpx.Response(200, content=b"not-json{{"))
    client = _http.build_client("testp", transport=transport)

    resp = await _http.request("testp", client, "GET", "https://example.test/x")

    assert resp.status_code == 200
    with pytest.raises(ValueError):
        resp.json()


async def test_user_agent_header_is_set():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["User-Agent"]
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    client = _http.build_client("expo", transport=transport)

    await _http.request("expo", client, "GET", "https://example.test/x")

    assert captured["ua"].startswith("parceltrack/")
    assert "(expo)" in captured["ua"]


async def test_4xx_other_than_429_401_403_returns_response():
    transport = _transport_returning(httpx.Response(404, json={"error": "missing"}))
    client = _http.build_client("testp", transport=transport)

    resp = await _http.request("testp", client, "GET", "https://example.test/x")

    assert resp.status_code == 404
