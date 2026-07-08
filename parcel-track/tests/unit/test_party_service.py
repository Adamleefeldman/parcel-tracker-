"""Unit tests for PartyService (mock-session style, per test_legal_entity_service)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.enums import PartyType
from app.db.models import AuditLog, LegalEntity, Party, PartyBankAccount
from app.schemas.schemas import PartyBankAccountCreate, PartyCreate, PartyUpdate
from app.services.party_service import PartyService


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


def _party(**kw):
    fields = {
        "id": uuid.uuid4(),
        "party_type": PartyType.SUPPLIER,
        "code": "SCDB",
        "name": "SCDB",
        "country": "Morocco",
        "default_currency_code": "USD",
        "is_active": True,
    }
    fields.update(kw)
    return Party(**fields)


@pytest.mark.asyncio
async def test_create_adds_party_and_audit():
    db = MagicMock()
    reloaded = _party(code="SCDB")
    # 1st execute: duplicate check (None). 2nd execute: get_or_404 reload.
    db.execute = AsyncMock(side_effect=[_result(None), _result(reloaded)])
    db.flush = AsyncMock()

    body = PartyCreate(
        party_type=PartyType.SUPPLIER,
        code="scdb",  # validator upper-cases
        name="SCDB",
        country="Morocco",
        default_currency_code="usd",  # validator upper-cases
    )
    result = await PartyService.create(db, body, _actor(), "9.9.9.9")

    added_party = next(o for o in _added(db) if isinstance(o, Party))
    assert added_party.code == "SCDB"
    assert added_party.party_type is PartyType.SUPPLIER
    assert added_party.default_currency_code == "USD"
    assert added_party.is_active is True
    audit = next(o for o in _added(db) if isinstance(o, AuditLog))
    assert audit.action == "party.created"
    assert audit.entity_code == "SCDB"  # audited by code, like the currency master
    assert audit.entity_id is None
    db.flush.assert_awaited_once()
    assert result is reloaded


@pytest.mark.asyncio
async def test_create_rejects_duplicate():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(_party()))  # existing (party_type, code)

    with pytest.raises(HTTPException) as exc:
        await PartyService.create(
            db,
            PartyCreate(party_type=PartyType.SUPPLIER, code="SCDB", name="Dup"),
            _actor(),
            None,
        )

    assert exc.value.status_code == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_update_applies_partial_and_audits():
    db = MagicMock()
    party = _party(name="SCDB", is_active=True)
    db.execute = AsyncMock(return_value=_result(party))  # get_or_404 (start + reload)
    db.flush = AsyncMock()

    result = await PartyService.update(db, party.id, PartyUpdate(is_active=False), _actor(), None)

    assert result.is_active is False
    assert result.name == "SCDB"  # untouched by the partial update
    audit = next(o for o in _added(db) if isinstance(o, AuditLog))
    assert audit.action == "party.updated"
    assert audit.entity_code == "SCDB"


@pytest.mark.asyncio
async def test_update_missing_raises_404():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(None))

    with pytest.raises(HTTPException) as exc:
        await PartyService.update(db, uuid.uuid4(), PartyUpdate(name="X"), _actor(), None)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_add_bank_account_first_is_default():
    db = MagicMock()
    party = _party(bank_accounts=[])  # no existing accounts
    db.execute = AsyncMock(side_effect=[_result(party), MagicMock()])  # load, then demote UPDATE
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    body = PartyBankAccountCreate(currency_code="USD", label="USD operating", is_default=False)
    account = await PartyService.add_bank_account(db, party.id, body, _actor(), None)

    assert account.is_default is True  # first account auto-defaults
    assert db.execute.await_count == 2  # get_or_404 + the demote UPDATE
    audit = next(o for o in _added(db) if isinstance(o, AuditLog))
    assert audit.action == "party.bank_account.added"


@pytest.mark.asyncio
async def test_add_bank_account_explicit_default_demotes():
    db = MagicMock()
    existing = PartyBankAccount(
        id=uuid.uuid4(), party_id=uuid.uuid4(), currency_code="USD", is_default=True
    )
    party = _party(bank_accounts=[existing])
    db.execute = AsyncMock(side_effect=[_result(party), MagicMock()])
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    body = PartyBankAccountCreate(currency_code="EUR", is_default=True)
    account = await PartyService.add_bank_account(db, party.id, body, _actor(), None)

    assert account.is_default is True
    assert db.execute.await_count == 2  # demote UPDATE issued to clear the prior default


@pytest.mark.asyncio
async def test_add_bank_account_non_default_when_others_exist():
    db = MagicMock()
    existing = PartyBankAccount(
        id=uuid.uuid4(), party_id=uuid.uuid4(), currency_code="USD", is_default=True
    )
    party = _party(bank_accounts=[existing])
    db.execute = AsyncMock(return_value=_result(party))  # only get_or_404; no demote UPDATE
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    body = PartyBankAccountCreate(currency_code="EUR", is_default=False)
    account = await PartyService.add_bank_account(db, party.id, body, _actor(), None)

    assert account.is_default is False
    assert db.execute.await_count == 1  # no demote UPDATE


@pytest.mark.asyncio
async def test_free_zone_watch_flags_only_uae_parties():
    db = MagicMock()
    entity = LegalEntity(
        code="FMCG_HUB",
        legal_name="WT Trading LLC",
        display_name="The FMCG Hub",
        jurisdiction="UAE Free Zone",
        is_active=True,
    )
    uae = _party(
        code="FF-DXB", party_type=PartyType.FREIGHT_FORWARDER, country="United Arab Emirates"
    )
    morocco = _party(code="SCDB", country="Morocco")
    db.execute = AsyncMock(side_effect=[_scalars([entity]), _scalars([uae, morocco])])

    out = await PartyService.free_zone_watch(db)

    assert len(out) == 1
    assert out[0].code == "FF-DXB"
    assert "Free Zone" in out[0].reason
    assert "FMCG_HUB" in out[0].reason  # names the trading entity in the note


@pytest.mark.asyncio
async def test_free_zone_watch_empty_without_free_zone_entity():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalars([])])  # no free-zone entity → short-circuit

    assert await PartyService.free_zone_watch(db) == []


def test_is_uae_recognises_aliases():
    assert PartyService._is_uae("UAE") is True
    assert PartyService._is_uae("United Arab Emirates") is True
    assert PartyService._is_uae("  u.a.e.  ") is True
    assert PartyService._is_uae("Morocco") is False
    assert PartyService._is_uae(None) is False


def test_mask_iban_keeps_last_four():
    assert PartyService._mask_iban("MA64011519000001205000534921") == "****4921"
    assert PartyService._mask_iban(None) is None
    assert PartyService._mask_iban("") is None


@pytest.mark.asyncio
async def test_list_all_returns_rows():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars([_party(code="SCDB"), _party(code="FF-DXB")]))

    out = await PartyService.list_all(db, party_type=PartyType.SUPPLIER)

    assert len(out) == 2  # filtering is SQL-side; the mock returns what it's handed
