"""Unit tests for app/integrations/vesselfinder.py.

Mirrors test_integrations_http.py's harness — httpx.MockTransport for the
wire layer, fakeredis for the circuit breaker. Zero real network.
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "x" * 64)

import httpx
import pytest

from app.integrations import _http, vesselfinder
from app.integrations._exceptions import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationRateLimited,
    IntegrationUnavailable,
)
from app.integrations.vesselfinder import VesselFinderClient

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
def _set_fleet_key(monkeypatch):
    """Default test key. Individual tests override to test the missing-key path."""
    from pydantic import SecretStr

    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "VESSELFINDER_FLEET_KEY", SecretStr("TEST_KEY_AABB"), raising=False)
    monkeypatch.setattr(s, "VESSELFINDER_BASE_URL", "https://api.vesselfinder.test", raising=False)
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


# A canonical /vesselslist response shape — matches VesselFinder docs.
_SAMPLE_RESPONSE: list[dict] = [
    {
        "AIS": {
            "MMSI": 304491000,
            "IMO": 9321483,
            "TIMESTAMP": "2026-04-30 10:00:00 UTC",
            "LATITUDE": 50.91,
            "LONGITUDE": -1.40,
            "COURSE": 287.0,
            "SPEED": 12.4,
            "HEADING": 287,
            "NAVSTAT": 0,
            "ETA": "2026-05-02 14:00:00",
            "DESTINATION": "GBSOU",
        }
    },
    {
        "AIS": {
            "MMSI": 304491001,
            "IMO": "9876543",
            "TIMESTAMP": "2026-04-30T09:55:00",
            "LATITUDE": 35.7,
            "LONGITUDE": -5.8,
            "COURSE": 90.0,
            "SPEED": 0.1,
            "HEADING": 511,
            "NAVSTAT": 5,
            "ETA": "",
            "DESTINATION": None,
        }
    },
]


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_get_fleet_positions_happy_path():
    transport = _transport_returning(httpx.Response(200, json=_SAMPLE_RESPONSE))
    client = VesselFinderClient(transport=transport)

    positions = await client.get_fleet_positions()

    assert len(positions) == 2

    p0 = positions[0]
    assert p0.imo == "9321483"
    assert p0.mmsi == 304491000
    assert p0.latitude == 50.91
    assert p0.navstat == 0
    assert p0.destination == "GBSOU"
    assert p0.timestamp is not None
    assert p0.timestamp.tzinfo is not None  # tz-aware UTC
    assert p0.eta is not None and p0.eta.year == 2026

    p1 = positions[1]
    assert p1.imo == "9876543"  # numeric coerced to str
    assert p1.eta is None  # empty string → None
    assert p1.destination is None
    assert p1.timestamp is not None  # ISO 8601 with T separator parses fine


async def test_missing_fleet_key_raises_auth_error(monkeypatch):
    from pydantic import SecretStr

    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "VESSELFINDER_FLEET_KEY", SecretStr(""), raising=False)

    client = VesselFinderClient()
    with pytest.raises(IntegrationAuthError):
        await client.get_fleet_positions()


async def test_userkey_passed_in_query_params():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["userkey"] = request.url.params.get("userkey", "")
        return httpx.Response(200, json=[])

    client = VesselFinderClient(transport=httpx.MockTransport(handler))
    await client.get_fleet_positions()

    assert captured["userkey"] == "TEST_KEY_AABB"
    assert captured["url"].startswith("https://api.vesselfinder.test/vesselslist")
    assert "format=json" in captured["url"]


async def test_401_raises_auth_error():
    transport = _transport_returning(httpx.Response(401))
    client = VesselFinderClient(transport=transport)

    with pytest.raises(IntegrationAuthError):
        await client.get_fleet_positions()


async def test_429_raises_rate_limited():
    transport = _transport_returning(httpx.Response(429, headers={"Retry-After": "30"}))
    client = VesselFinderClient(transport=transport)

    with pytest.raises(IntegrationRateLimited) as exc_info:
        await client.get_fleet_positions()

    assert exc_info.value.retry_after_seconds == 30


async def test_5xx_after_retries_raises_unavailable():
    transport = _transport_returning(httpx.Response(503))
    client = VesselFinderClient(transport=transport)

    with pytest.raises(IntegrationUnavailable):
        await client.get_fleet_positions()


async def test_malformed_json_raises_integration_error():
    transport = _transport_returning(httpx.Response(200, content=b"not-json{{"))
    client = VesselFinderClient(transport=transport)

    with pytest.raises(IntegrationError):
        await client.get_fleet_positions()


async def test_unexpected_payload_type_raises_integration_error():
    # VF docs guarantee a list; an object means the contract changed.
    transport = _transport_returning(httpx.Response(200, json={"error": "bad request"}))
    client = VesselFinderClient(transport=transport)

    with pytest.raises(IntegrationError):
        await client.get_fleet_positions()


async def test_item_missing_imo_is_skipped():
    transport = _transport_returning(
        httpx.Response(
            200,
            json=[
                {"AIS": {"MMSI": 1, "IMO": 0, "LATITUDE": 0, "LONGITUDE": 0}},
                _SAMPLE_RESPONSE[0],
            ],
        )
    )
    client = VesselFinderClient(transport=transport)

    positions = await client.get_fleet_positions()

    assert len(positions) == 1
    assert positions[0].imo == "9321483"


async def test_unparseable_timestamp_yields_none_not_exception():
    transport = _transport_returning(
        httpx.Response(
            200,
            json=[
                {
                    "AIS": {
                        "IMO": 1234567,
                        "MMSI": 999,
                        "TIMESTAMP": "not-a-date",
                        "LATITUDE": 0.0,
                        "LONGITUDE": 0.0,
                    }
                }
            ],
        )
    )
    client = VesselFinderClient(transport=transport)

    positions = await client.get_fleet_positions()

    assert len(positions) == 1
    assert positions[0].timestamp is None


async def test_user_agent_includes_provider():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["User-Agent"]
        return httpx.Response(200, json=[])

    client = VesselFinderClient(transport=httpx.MockTransport(handler))
    await client.get_fleet_positions()

    assert "(vesselfinder)" in captured["ua"]


# ── Pure helper coverage ──────────────────────────────────────────────────────


def test_parse_vf_datetime_handles_known_shapes():
    f = vesselfinder._parse_vf_datetime
    assert f("2026-04-30 10:00:00 UTC") is not None
    assert f("2026-04-30 10:00:00") is not None
    assert f("2026-04-30T10:00:00") is not None
    assert f("") is None
    assert f(None) is None
    assert f("garbage") is None
    assert f(0) is None


def test_coerce_int_and_float_tolerate_strings():
    assert vesselfinder._coerce_int("42") == 42
    assert vesselfinder._coerce_int("") is None
    assert vesselfinder._coerce_int(None) is None
    assert vesselfinder._coerce_float("3.14") == 3.14
    assert vesselfinder._coerce_float(None) is None
