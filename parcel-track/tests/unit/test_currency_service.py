"""Unit tests for CurrencyService (mock-session style, per test_port_template_service)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.db.models import AuditLog, CurrencyRef
from app.schemas.schemas import CurrencyCreate, CurrencyUpdate
from app.services.currency_service import CurrencyService


def _result(value):
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


def _scalars(values):
    m = MagicMock()
    m.scalars.return_value.all.return_value = values
    return m


def _actor():
    actor = MagicMock()
    actor.id = uuid.uuid4()
    return actor


def _added(db):
    return [call.args[0] for call in db.add.call_args_list]


@pytest.mark.asyncio
async def test_create_adds_currency_and_audit():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(None))  # no existing currency
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    body = CurrencyCreate(code="aed", name="UAE Dirham", symbol="AED", minor_units=2)
    result = await CurrencyService.create(db, body, _actor(), "9.9.9.9")

    assert isinstance(result, CurrencyRef)
    assert result.code == "AED"  # validator upper-cased it
    assert result.is_base is False
    added = _added(db)
    assert any(isinstance(o, CurrencyRef) for o in added)
    audit = next(o for o in added if isinstance(o, AuditLog))
    assert audit.action == "currency.created"
    assert audit.entity_code == "AED"
    assert audit.entity_id is None
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_rejects_duplicate():
    db = MagicMock()
    existing = CurrencyRef(code="USD", name="US Dollar", is_base=True)
    db.execute = AsyncMock(return_value=_result(existing))

    with pytest.raises(HTTPException) as exc:
        await CurrencyService.create(db, CurrencyCreate(code="USD", name="Dup"), _actor(), None)

    assert exc.value.status_code == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_update_applies_partial_and_audits():
    db = MagicMock()
    currency = CurrencyRef(
        code="GBP", name="Pound", symbol="£", minor_units=2, is_base=False, is_active=True
    )
    db.execute = AsyncMock(return_value=_result(currency))
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    result = await CurrencyService.update(
        db, "gbp", CurrencyUpdate(is_active=False), _actor(), None
    )

    assert result.is_active is False
    assert result.name == "Pound"  # untouched by the partial update
    audit = next(o for o in _added(db) if isinstance(o, AuditLog))
    assert audit.action == "currency.updated"
    assert audit.entity_code == "GBP"


@pytest.mark.asyncio
async def test_update_missing_raises_404():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(None))

    with pytest.raises(HTTPException) as exc:
        await CurrencyService.update(db, "ZZZ", CurrencyUpdate(name="X"), _actor(), None)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_active_only():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars([CurrencyRef(code="USD", name="US Dollar")]))

    out = await CurrencyService.list_all(db, active_only=True)

    assert len(out) == 1
    assert out[0].code == "USD"
