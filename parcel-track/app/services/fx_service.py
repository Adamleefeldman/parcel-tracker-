"""FX-rate service (Data-Foundation Pillar 1b).

Reads/writes the append-only `fx_rates` table and answers "what is X in USD?".
Base is always USD (our reporting base). The poller stores one snapshot per
provider update; `rate_to_usd` returns the factor Pillar 1c will freeze onto a
transaction so reports never re-convert historical rows.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CurrencyRef, FxRate
from app.integrations.exchangerate_api import PROVIDER, ExchangeRateApiClient

BASE_CODE = "USD"


class FxService:
    @staticmethod
    async def get_rate(
        db: AsyncSession, quote_code: str, as_of: datetime | None = None
    ) -> FxRate | None:
        """Latest fx_rates row for `quote_code` at/under `as_of` (or overall latest)."""
        stmt = select(FxRate).where(FxRate.quote_code == quote_code.upper())
        if as_of is not None:
            stmt = stmt.where(FxRate.as_of <= as_of)
        stmt = stmt.order_by(FxRate.as_of.desc()).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def rate_to_usd(
        db: AsyncSession, currency_code: str, at: datetime | None = None
    ) -> Decimal | None:
        """Factor to multiply a `currency_code` amount by to get USD.

        Rates are stored as `1 USD = rate quote`, so native→USD = 1 / rate. USD
        itself is the base (factor 1). Returns None when no rate is available.
        """
        code = currency_code.upper()
        if code == BASE_CODE:
            return Decimal(1)
        row = await FxService.get_rate(db, code, as_of=at)
        if row is None or row.rate == 0:
            return None
        return Decimal(1) / row.rate

    @staticmethod
    async def list_rates(
        db: AsyncSession, *, quote: str | None = None, limit: int = 100
    ) -> list[FxRate]:
        stmt = select(FxRate)
        if quote is not None:
            stmt = stmt.where(FxRate.quote_code == quote.upper())
        stmt = stmt.order_by(FxRate.as_of.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def latest_per_quote(db: AsyncSession) -> list[FxRate]:
        """The most recent row for each quote currency present in the table."""
        codes_result = await db.execute(select(FxRate.quote_code).distinct())
        latest: list[FxRate] = []
        for (code,) in codes_result.all():
            row = await FxService.get_rate(db, code)
            if row is not None:
                latest.append(row)
        latest.sort(key=lambda r: r.quote_code)
        return latest

    @staticmethod
    async def poll_once(
        db: AsyncSession, *, client: ExchangeRateApiClient | None = None
    ) -> dict[str, Any]:
        """Fetch the latest USD-base rates and append one snapshot to fx_rates.

        Idempotent per provider update: if a row already exists at the provider's
        last-update `as_of`, nothing is inserted. Only currencies that are active
        in the master (`currencies`) are stored.
        """
        client = client or ExchangeRateApiClient()
        snapshot = await client.get_latest_rates(BASE_CODE)

        existing = await db.execute(
            select(FxRate.id)
            .where(FxRate.base_code == snapshot.base, FxRate.as_of == snapshot.as_of)
            .limit(1)
        )
        if existing.first() is not None:
            return {
                "inserted": 0,
                "skipped": "already_stored",
                "as_of": snapshot.as_of.isoformat(),
            }

        active = await db.execute(select(CurrencyRef.code).where(CurrencyRef.is_active.is_(True)))
        tracked = {code for (code,) in active.all()} - {snapshot.base}

        inserted = 0
        missing: list[str] = []
        for code in sorted(tracked):
            rate = snapshot.rates.get(code)
            if rate is None:
                missing.append(code)
                continue
            db.add(
                FxRate(
                    base_code=snapshot.base,
                    quote_code=code,
                    rate=rate,
                    as_of=snapshot.as_of,
                    source=PROVIDER,
                )
            )
            inserted += 1
        await db.flush()

        summary: dict[str, Any] = {"inserted": inserted, "as_of": snapshot.as_of.isoformat()}
        if missing:
            summary["missing"] = missing
        return summary
