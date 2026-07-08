"""Unit tests for LegalEntityService (mock-session style, per test_currency_service)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.db.models import AuditLog, LegalEntity
from app.schemas.schemas import LegalEntityCreate, LegalEntityUpdate
from app.services.legal_entity_service import LegalEntityService


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
async def test_create_adds_entity_and_audit():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(None))  # no existing entity with this code
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    body = LegalEntityCreate(
        code="morocco",
        legal_name="WT Trading Morocco SARL",
        display_name="The FMCG Hub Morocco",
        jurisdiction="Morocco",
        base_currency_code="usd",
    )
    result = await LegalEntityService.create(db, body, _actor(), "9.9.9.9")

    assert isinstance(result, LegalEntity)
    assert result.code == "MOROCCO"  # validator upper-cased it
    assert result.base_currency_code == "USD"
    assert result.is_default is False  # is_default is never settable via the API
    audit = next(o for o in _added(db) if isinstance(o, AuditLog))
    assert audit.action == "legal_entity.created"
    assert audit.entity_code == "MOROCCO"  # audited by code, like currency master
    assert audit.entity_id is None
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_rejects_duplicate():
    db = MagicMock()
    existing = LegalEntity(
        code="FMCG_HUB", legal_name="WT Trading LLC", display_name="The FMCG Hub", is_default=True
    )
    db.execute = AsyncMock(return_value=_result(existing))

    with pytest.raises(HTTPException) as exc:
        await LegalEntityService.create(
            db,
            LegalEntityCreate(code="FMCG_HUB", legal_name="Dup", display_name="Dup"),
            _actor(),
            None,
        )

    assert exc.value.status_code == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_update_applies_partial_and_audits():
    db = MagicMock()
    entity = LegalEntity(
        id=uuid.uuid4(),
        code="FMCG_HUB",
        legal_name="WT Trading LLC",
        display_name="The FMCG Hub",
        jurisdiction="UAE Free Zone",
        base_currency_code="USD",
        is_default=True,
        is_active=True,
    )
    db.execute = AsyncMock(return_value=_result(entity))
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    result = await LegalEntityService.update(
        db, entity.id, LegalEntityUpdate(is_active=False), _actor(), None
    )

    assert result.is_active is False
    assert result.legal_name == "WT Trading LLC"  # untouched by the partial update
    audit = next(o for o in _added(db) if isinstance(o, AuditLog))
    assert audit.action == "legal_entity.updated"
    assert audit.entity_code == "FMCG_HUB"


@pytest.mark.asyncio
async def test_update_missing_raises_404():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(None))

    with pytest.raises(HTTPException) as exc:
        await LegalEntityService.update(
            db, uuid.uuid4(), LegalEntityUpdate(legal_name="X"), _actor(), None
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_default_and_default_id():
    db = MagicMock()
    default = LegalEntity(
        id=uuid.uuid4(),
        code="FMCG_HUB",
        legal_name="WT Trading LLC",
        display_name="The FMCG Hub",
        is_default=True,
    )
    db.execute = AsyncMock(return_value=_result(default))

    assert await LegalEntityService.get_default(db) is default
    assert await LegalEntityService.default_id(db) == default.id


@pytest.mark.asyncio
async def test_default_id_none_when_unseeded():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(None))

    assert await LegalEntityService.default_id(db) is None


@pytest.mark.asyncio
async def test_list_active_only():
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_scalars(
            [LegalEntity(code="FMCG_HUB", legal_name="WT Trading LLC", display_name="The FMCG Hub")]
        )
    )

    out = await LegalEntityService.list_all(db, active_only=True)

    assert len(out) == 1
    assert out[0].code == "FMCG_HUB"
