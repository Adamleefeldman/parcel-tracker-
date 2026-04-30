"""VesselFinder AIS API client.

Wraps the `/vesselslist` endpoint, which returns AIS positions for every
vessel in the account's predefined fleet in one call. The fleet is managed
out-of-band (via the VesselFinder dashboard) — this client only reads.

Why /vesselslist and not /vessels?
    /vessels?imo=… is credit-metered (1 credit per terrestrial position).
    /vesselslist is included in the fleet subscription with no per-call cost,
    so cadence is bounded only by the subscription tier. We pay either way,
    but the bulk endpoint is materially cheaper at the polling cadence we
    need (≤ 30 min).

Status derivation is intentionally NOT done here. The API returns AIS
NAVSTAT integers (0-15) plus position + ETA — translating those into our
domain `VesselUpdateStatus` requires the destination port and stored ETA,
which only the service layer has. This keeps the client a thin wire-format
adapter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.integrations._exceptions import IntegrationError
from app.integrations._http import build_client, request

logger = logging.getLogger("parceltrack.integrations.vesselfinder")

PROVIDER = "vesselfinder"


@dataclass(frozen=True, slots=True)
class FleetVesselPosition:
    """One vessel's AIS snapshot from /vesselslist.

    Fields mirror the VF response with two cleanups:
      - `imo` is normalised to a string (the API returns it as a string but
        we want the type system to enforce that downstream).
      - timestamps are parsed to timezone-aware UTC datetimes so the service
        layer never deals with the wire format.

    Anything VF didn't return is None — most callers only need imo + position
    + navstat + eta, but we surface speed/course/heading too for future use
    (e.g. estimating whether a stationary vessel is genuinely arrived vs
    drifting at anchor outside port limits).
    """

    imo: str
    mmsi: int | None
    timestamp: datetime | None
    latitude: float | None
    longitude: float | None
    course: float | None
    speed: float | None
    heading: int | None
    navstat: int | None
    eta: datetime | None
    destination: str | None


def _parse_vf_datetime(value: Any) -> datetime | None:
    """Parse VesselFinder's wire format.

    Two shapes appear in their docs and historical responses:
      - "2017-08-11 11:15:15 UTC"  (TIMESTAMP — space separator + UTC suffix)
      - "2017-08-12 03:00:00"      (ETA — naive, documented as UTC)
      - ISO 8601 with "T" separator (some satellite feeds)

    Returns None for missing / unparseable values rather than raising — a
    single bad timestamp shouldn't kill a poll cycle for the whole fleet.
    """
    if value in (None, "", "0", 0):
        return None
    if not isinstance(value, str):
        return None

    # Strip a trailing " UTC" — fromisoformat doesn't accept it.
    cleaned = value.removesuffix(" UTC").replace("T", " ").strip()
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        logger.warning("vesselfinder_unparseable_datetime", extra={"value": value})
        return None

    # All VF timestamps are documented as UTC. Naive datetimes get the UTC
    # tzinfo attached so downstream comparisons are unambiguous.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _coerce_int(value: Any) -> int | None:
    """VF sometimes returns numeric fields as strings; coerce safely."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_one(item: dict[str, Any]) -> FleetVesselPosition | None:
    """Map one VF response item to our dataclass.

    The wire format wraps the AIS dict under an "AIS" key (and optionally
    "MASTERDATA" / "VOYAGE" if `extradata` is set). We only consume AIS;
    if the item is missing AIS or IMO entirely we skip it (logged) — better
    to drop one vessel than abort the cycle.
    """
    ais = item.get("AIS") or item
    imo_raw = ais.get("IMO") or item.get("IMO")
    if imo_raw in (None, "", 0, "0"):
        logger.warning("vesselfinder_item_missing_imo", extra={"raw": item})
        return None

    return FleetVesselPosition(
        imo=str(imo_raw),
        mmsi=_coerce_int(ais.get("MMSI")),
        timestamp=_parse_vf_datetime(ais.get("TIMESTAMP")),
        latitude=_coerce_float(ais.get("LATITUDE")),
        longitude=_coerce_float(ais.get("LONGITUDE")),
        course=_coerce_float(ais.get("COURSE")),
        speed=_coerce_float(ais.get("SPEED")),
        heading=_coerce_int(ais.get("HEADING")),
        navstat=_coerce_int(ais.get("NAVSTAT")),
        eta=_parse_vf_datetime(ais.get("ETA")),
        destination=ais.get("DESTINATION") or None,
    )


class VesselFinderClient:
    """Async client for VesselFinder's fleet endpoint.

    Construct once per task invocation; the underlying httpx client is
    short-lived and the circuit breaker state lives in Redis.
    """

    def __init__(self, *, transport: Any | None = None) -> None:
        # Transport is an injection point for tests (`httpx.MockTransport`).
        self._transport = transport

    async def get_fleet_positions(self) -> list[FleetVesselPosition]:
        """Fetch AIS positions for every vessel in the configured fleet.

        Raises:
            IntegrationAuthError: fleet key missing or rejected (401/403).
            IntegrationRateLimited: 429 — caller should back off.
            IntegrationUnavailable: 5xx after retries, network error, or
                circuit open.
            IntegrationTimeout: timeout after retries.
            IntegrationError: malformed / non-list JSON response.
        """
        settings = get_settings()
        fleet_key = settings.VESSELFINDER_FLEET_KEY.get_secret_value()
        if not fleet_key:
            # Fail loudly rather than send a request with userkey="" that
            # would hit the API and burn a 401. Configuration error, not
            # a runtime fault — but raise IntegrationAuthError so callers
            # treat it the same way (don't retry, page ops).
            from app.integrations._exceptions import IntegrationAuthError

            raise IntegrationAuthError(
                "VESSELFINDER_FLEET_KEY is not configured", provider=PROVIDER
            )

        url = f"{settings.VESSELFINDER_BASE_URL.rstrip('/')}/vesselslist"
        # Note: `userkey` is in the query string per VF's API contract. The
        # shared HTTP helper already strips query params from log lines, so
        # the key won't appear in structured logs.
        params = {"userkey": fleet_key, "format": "json"}

        async with build_client(PROVIDER, transport=self._transport) as client:
            response = await request(PROVIDER, client, "GET", url, params=params)

        # 2xx with a non-list body indicates either an API contract change or
        # an upstream proxy injecting an error doc — surface it as an error.
        try:
            payload = response.json()
        except ValueError as exc:
            raise IntegrationError(
                f"VesselFinder returned non-JSON body (status {response.status_code})",
                provider=PROVIDER,
            ) from exc

        if not isinstance(payload, list):
            raise IntegrationError(
                f"VesselFinder returned unexpected payload type: {type(payload).__name__}",
                provider=PROVIDER,
            )

        positions: list[FleetVesselPosition] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            parsed = _parse_one(item)
            if parsed is not None:
                positions.append(parsed)

        logger.info(
            "vesselfinder_fleet_positions_fetched",
            extra={"vessel_count": len(positions)},
        )
        return positions
