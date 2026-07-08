"""Unit tests for app/integrations/exchangerate_api.py.

Mirrors test_vesselfinder_client.py — httpx.MockTransport for the wire layer,
fakeredis for the circuit breaker. Zero real network.
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "x" * 64)

from decimal import Decimal

import httpx
import pytest

from app.integrations import _http
from app.integrations._exceptions import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationRateLimited,
    IntegrationUnavailable,
)
from app.integrations.exchangerate_api import ExchangeRateApiClient

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(_http, "_sleep", _instant)


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    try:
        import fakeredis.aioredis as fakeredis_aio
    except ImportError:
        pytest.skip("fakeredis not installed — skipping breaker tests")

    client = fakeredis_aio.FakeRedis(decode_responses=True)
    monkeypatch.setattr(_http, "get_redis_client", lambda: client)
    yield client


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    """Default test key. Individual tests override to test the missing-key path."""
    from pydantic import SecretStr

    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "EXCHANGERATE_API_KEY", SecretStr("TEST_KEY_123"), raising=False)
    monkeypatch.setattr(s, "EXCHANGERATE_API_BASE_URL", "https://fx.test/v6", raising=False)
    yield


def _transport_returning(*responses: httpx.Response) -> httpx.MockTransport:
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


# 1767225600 == 2026-01-01 00:00:00 UTC
_SUCCESS: dict = {
    "result": "success",
    "time_last_update_unix": 1767225600,
    "base_code": "USD",
    "conversion_rates": {"USD": 1, "GBP": 0.7893, "EUR": 0.9013, "MAD": 9.87, "AED": 3.6725},
}


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_get_latest_rates_happy_path():
    transport = _transport_returning(httpx.Response(200, json=_SUCCESS))
    snap = await ExchangeRateApiClient(transport=transport).get_latest_rates("USD")

    assert snap.base == "USD"
    # parse_float=Decimal preserves the exact wire digits — no float drift.
    assert snap.rates["GBP"] == Decimal("0.7893")
    assert snap.rates["AED"] == Decimal("3.6725")
    assert snap.rates["USD"] == Decimal("1")
    assert snap.as_of.tzinfo is not None
    assert (snap.as_of.year, snap.as_of.month, snap.as_of.day) == (2026, 1, 1)


async def test_missing_key_raises_auth_error(monkeypatch):
    from pydantic import SecretStr

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "EXCHANGERATE_API_KEY", SecretStr(""), raising=False)

    with pytest.raises(IntegrationAuthError):
        await ExchangeRateApiClient().get_latest_rates()


async def test_key_and_base_in_url_path():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_SUCCESS)

    await ExchangeRateApiClient(transport=httpx.MockTransport(handler)).get_latest_rates("USD")

    assert captured["url"] == "https://fx.test/v6/TEST_KEY_123/latest/USD"


async def test_result_error_invalid_key_raises_auth():
    body = {"result": "error", "error-type": "invalid-key"}
    transport = _transport_returning(httpx.Response(200, json=body))
    with pytest.raises(IntegrationAuthError):
        await ExchangeRateApiClient(transport=transport).get_latest_rates()


async def test_result_error_quota_raises_rate_limited():
    body = {"result": "error", "error-type": "quota-reached"}
    transport = _transport_returning(httpx.Response(200, json=body))
    with pytest.raises(IntegrationRateLimited):
        await ExchangeRateApiClient(transport=transport).get_latest_rates()


async def test_result_error_other_raises_integration_error():
    body = {"result": "error", "error-type": "unsupported-code"}
    transport = _transport_returning(httpx.Response(200, json=body))
    with pytest.raises(IntegrationError):
        await ExchangeRateApiClient(transport=transport).get_latest_rates()


async def test_401_raises_auth_error():
    transport = _transport_returning(httpx.Response(401))
    with pytest.raises(IntegrationAuthError):
        await ExchangeRateApiClient(transport=transport).get_latest_rates()


async def test_429_raises_rate_limited():
    transport = _transport_returning(httpx.Response(429, headers={"Retry-After": "30"}))
    with pytest.raises(IntegrationRateLimited) as exc_info:
        await ExchangeRateApiClient(transport=transport).get_latest_rates()
    assert exc_info.value.retry_after_seconds == 30


async def test_5xx_after_retries_raises_unavailable():
    transport = _transport_returning(httpx.Response(503))
    with pytest.raises(IntegrationUnavailable):
        await ExchangeRateApiClient(transport=transport).get_latest_rates()


async def test_malformed_json_raises_integration_error():
    transport = _transport_returning(httpx.Response(200, content=b"not-json{{"))
    with pytest.raises(IntegrationError):
        await ExchangeRateApiClient(transport=transport).get_latest_rates()


async def test_non_dict_payload_raises_integration_error():
    transport = _transport_returning(httpx.Response(200, json=[1, 2, 3]))
    with pytest.raises(IntegrationError):
        await ExchangeRateApiClient(transport=transport).get_latest_rates()


async def test_missing_conversion_rates_raises():
    body = {"result": "success", "time_last_update_unix": 1767225600, "base_code": "USD"}
    transport = _transport_returning(httpx.Response(200, json=body))
    with pytest.raises(IntegrationError):
        await ExchangeRateApiClient(transport=transport).get_latest_rates()


async def test_user_agent_includes_provider():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["User-Agent"]
        return httpx.Response(200, json=_SUCCESS)

    await ExchangeRateApiClient(transport=httpx.MockTransport(handler)).get_latest_rates()

    assert "(exchangerate_api)" in captured["ua"]
