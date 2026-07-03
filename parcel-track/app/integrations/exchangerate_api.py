"""ExchangeRate-API FX-rate client.

Wraps the `/v6/{key}/latest/{base}` endpoint, which returns every conversion rate
for `base` in one call (`1 base = rate quote`). We request base=USD (our reporting
base) and the service layer stores the rates we track.

Chosen over XE for cost: ExchangeRate-API's free tier is commercial-use-OK, covers
all our currencies (incl. the hard-to-source MAD + the USD-pegged AED), and one call
returns everything.

Thin wire adapter — no persistence or business logic here (that is `FxService`).
Rates are parsed with `parse_float=Decimal` so no binary-float imprecision ever
enters the money path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.integrations._exceptions import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationRateLimited,
)
from app.integrations._http import build_client, request

logger = logging.getLogger("parceltrack.integrations.exchangerate_api")

PROVIDER = "exchangerate_api"


@dataclass(frozen=True, slots=True)
class FxRateSnapshot:
    """One fetch of latest rates.

    `rates` maps quote code -> rate, where `1 base = rate quote`. `as_of` is the
    provider's own last-update time (tz-aware UTC) — using it as the row timestamp
    lets the poller dedupe (one stored snapshot per provider update).
    """

    base: str
    as_of: datetime
    rates: dict[str, Decimal]


class ExchangeRateApiClient:
    """Async client for ExchangeRate-API's latest-rates endpoint.

    Construct once per task invocation; the httpx client is short-lived and the
    circuit-breaker state lives in Redis (shared HTTP helper).
    """

    def __init__(self, *, transport: Any | None = None) -> None:
        # Transport is an injection point for tests (`httpx.MockTransport`).
        self._transport = transport

    async def get_latest_rates(self, base: str = "USD") -> FxRateSnapshot:
        """Fetch latest conversion rates for `base`.

        Raises:
            IntegrationAuthError: key missing / invalid / inactive account (or 401/403).
            IntegrationRateLimited: quota reached (429 or result=error quota-reached).
            IntegrationUnavailable / IntegrationTimeout: transient (from the HTTP helper).
            IntegrationError: malformed body or a non-success result payload.
        """
        settings = get_settings()
        api_key = settings.EXCHANGERATE_API_KEY.get_secret_value()
        if not api_key:
            # Fail loudly rather than hit the API with an empty key and burn a 403.
            # Config error, but raise IntegrationAuthError so callers treat it the
            # same way (don't retry).
            raise IntegrationAuthError("EXCHANGERATE_API_KEY is not configured", provider=PROVIDER)

        base = base.upper()
        # Key is in the path per ExchangeRate-API's contract. Our HTTP helper does
        # not log request URLs, so it does not leak into structured logs.
        url = f"{settings.EXCHANGERATE_API_BASE_URL.rstrip('/')}/{api_key}/latest/{base}"

        async with build_client(PROVIDER, transport=self._transport) as client:
            response = await request(PROVIDER, client, "GET", url)

        # parse_float=Decimal keeps the exact wire digits — never Decimal(float).
        try:
            payload: Any = json.loads(response.text, parse_float=Decimal)
        except ValueError as exc:
            raise IntegrationError(
                f"ExchangeRate-API returned non-JSON body (status {response.status_code})",
                provider=PROVIDER,
            ) from exc

        if not isinstance(payload, dict):
            raise IntegrationError(
                f"ExchangeRate-API returned unexpected payload type: {type(payload).__name__}",
                provider=PROVIDER,
            )

        if payload.get("result") != "success":
            error_type = str(payload.get("error-type", "unknown"))
            if error_type in ("invalid-key", "inactive-account"):
                raise IntegrationAuthError(
                    f"ExchangeRate-API auth error: {error_type}", provider=PROVIDER
                )
            if error_type == "quota-reached":
                raise IntegrationRateLimited("ExchangeRate-API quota reached", provider=PROVIDER)
            raise IntegrationError(f"ExchangeRate-API error: {error_type}", provider=PROVIDER)

        rates_raw = payload.get("conversion_rates")
        if not isinstance(rates_raw, dict):
            raise IntegrationError(
                "ExchangeRate-API response missing conversion_rates", provider=PROVIDER
            )

        rates: dict[str, Decimal] = {}
        for code, value in rates_raw.items():
            if isinstance(value, Decimal):
                rates[code] = value
            elif isinstance(value, (int, float)):
                rates[code] = Decimal(str(value))
            # Non-numeric values are skipped rather than aborting the whole fetch.

        as_of = self._parse_as_of(payload.get("time_last_update_unix"))
        logger.info(
            "exchangerate_api_rates_fetched",
            extra={"base": base, "rate_count": len(rates), "as_of": as_of.isoformat()},
        )
        return FxRateSnapshot(base=base, as_of=as_of, rates=rates)

    @staticmethod
    def _parse_as_of(unix: Any) -> datetime:
        """Provider's last-update epoch → tz-aware UTC; falls back to now() if absent."""
        try:
            if unix is not None:
                return datetime.fromtimestamp(int(unix), tz=UTC)
        except (TypeError, ValueError, OverflowError, OSError):
            logger.warning("exchangerate_api_unparseable_as_of", extra={"value": unix})
        return datetime.now(UTC)
