"""Unit tests for FxService (mock-session style, per test_currency_service)."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import FxRate
from app.integrations.exchangerate_api import FxRateSnapshot
from app.services.fx_service import FxService


def _scalar(value):
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


def _rows(values):
    """A result whose .all()/.first() behave like a row set."""
    m = MagicMock()
    m.all.return_value = list(values)
    m.first.return_value = values[0] if values else None
    return m


@pytest.mark.asyncio
async def test_rate_to_usd_base_is_one():
    db = MagicMock()
    db.execute = AsyncMock()
    assert await FxService.rate_to_usd(db, "USD") == Decimal(1)
    db.execute.assert_not_called()  # base short-circuits, no query


@pytest.mark.asyncio
async def test_rate_to_usd_inverts_stored_rate():
    db = MagicMock()
    row = FxRate(
        base_code="USD",
        quote_code="GBP",
        rate=Decimal("0.80"),
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db.execute = AsyncMock(return_value=_scalar(row))

    factor = await FxService.rate_to_usd(db, "gbp")

    assert factor == Decimal(1) / Decimal("0.80")  # 1 USD = 0.80 GBP → £1 = $1.25


@pytest.mark.asyncio
async def test_rate_to_usd_none_when_no_rate():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar(None))
    assert await FxService.rate_to_usd(db, "MAD") is None


@pytest.mark.asyncio
async def test_poll_once_inserts_tracked_and_reports_missing():
    snap = FxRateSnapshot(
        base="USD",
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        rates={
            "USD": Decimal(1),
            "GBP": Decimal("0.79"),
            "EUR": Decimal("0.90"),
            "XYZ": Decimal("2"),
        },
    )
    fake_client = SimpleNamespace(get_latest_rates=AsyncMock(return_value=snap))
    db = MagicMock()
    db.flush = AsyncMock()
    # 1st execute = dedupe (none exist); 2nd = active currency codes.
    db.execute = AsyncMock(
        side_effect=[_rows([]), _rows([("USD",), ("GBP",), ("EUR",), ("MAD",), ("AED",)])]
    )

    summary = await FxService.poll_once(db, client=fake_client)

    added = [call.args[0] for call in db.add.call_args_list]
    # GBP + EUR only: USD is the base, MAD/AED absent from the snapshot, XYZ untracked.
    assert {a.quote_code for a in added} == {"GBP", "EUR"}
    assert summary["inserted"] == 2
    assert sorted(summary["missing"]) == ["AED", "MAD"]
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_once_skips_when_as_of_already_stored():
    snap = FxRateSnapshot(
        base="USD", as_of=datetime(2026, 1, 1, tzinfo=UTC), rates={"GBP": Decimal("0.79")}
    )
    fake_client = SimpleNamespace(get_latest_rates=AsyncMock(return_value=snap))
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=_rows([("existing-id",)]))  # dedupe finds a row

    summary = await FxService.poll_once(db, client=fake_client)

    assert summary["inserted"] == 0
    assert summary["skipped"] == "already_stored"
    db.add.assert_not_called()
