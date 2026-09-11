"""Integration: Pillar 3 party master — real route -> service path on SQLite.

Covers party + bank-account CRUD, the bank default-flip, the optional
`supplier_party_id` wiring on PO create (must be an active SUPPLIER), and the
V1 UAE Free-Zone watch report. create_all builds the tables but not the
migration seeds, so reference rows (USD, a free-zone entity) are inserted here.
"""

import uuid

import pytest
from sqlalchemy import select

from app.db.models import CurrencyRef, LegalEntity, PurchaseOrder
from tests.integration.conftest import TestSession


async def _seed_usd() -> None:
    async with TestSession() as db:
        db.add(CurrencyRef(code="USD", name="US Dollar", is_base=True))
        await db.commit()


async def _seed_free_zone_entity() -> None:
    """A UAE Free-Zone trading entity (assumes USD already seeded)."""
    async with TestSession() as db:
        db.add(
            LegalEntity(
                code="FMCG_HUB",
                legal_name="WT Trading LLC",
                display_name="The FMCG Hub",
                jurisdiction="UAE Free Zone",
                base_currency_code="USD",
                is_default=True,
                is_active=True,
            )
        )
        await db.commit()


async def _create_party(client, h, **overrides) -> dict:
    payload = {
        "party_type": "supplier",
        "code": "SCDB",
        "name": "SCDB",
        "country": "Morocco",
    }
    payload.update(overrides)
    r = await client.post("/api/v1/parties", json=payload, headers=h)
    assert r.status_code == 200, r.json()
    return r.json()


@pytest.mark.asyncio
async def test_create_party_and_bank_account(client, admin_token):
    await _seed_usd()
    h = {"Authorization": f"Bearer {admin_token}"}

    party = await _create_party(
        client,
        h,
        code="scdb",  # lower-case → validator upper-cases it
        default_currency_code="usd",
        default_payment_terms="Net 30",
        email="ops@scdb.example",
    )
    assert party["code"] == "SCDB"
    assert party["party_type"] == "supplier"
    assert party["default_currency_code"] == "USD"
    assert party["bank_accounts"] == []
    pid = party["id"]

    r = await client.post(
        f"/api/v1/parties/{pid}/bank-accounts",
        json={
            "currency_code": "usd",
            "label": "USD operating",
            "bank_name": "Attijariwafa Bank",
            "account_name": "SCDB SARL",
            "iban": "MA64011519000001205000534921",
            "swift_bic": "BCMAMAMC",
        },
        headers=h,
    )
    assert r.status_code == 200, r.json()
    account = r.json()
    assert account["is_default"] is True  # first account auto-defaults
    assert account["currency_code"] == "USD"

    r = await client.get(f"/api/v1/parties/{pid}", headers=h)
    assert r.status_code == 200
    accounts = r.json()["bank_accounts"]
    assert len(accounts) == 1
    assert accounts[0]["is_default"] is True


@pytest.mark.asyncio
async def test_bank_account_explicit_default_demotes_prior(client, admin_token):
    await _seed_usd()
    h = {"Authorization": f"Bearer {admin_token}"}
    pid = (await _create_party(client, h))["id"]

    r = await client.post(
        f"/api/v1/parties/{pid}/bank-accounts",
        json={"currency_code": "usd", "label": "first"},
        headers=h,
    )
    assert r.status_code == 200, r.json()

    r = await client.post(
        f"/api/v1/parties/{pid}/bank-accounts",
        json={"currency_code": "usd", "label": "second", "is_default": True},
        headers=h,
    )
    assert r.status_code == 200, r.json()

    r = await client.get(f"/api/v1/parties/{pid}", headers=h)
    accounts = r.json()["bank_accounts"]
    defaults = [a for a in accounts if a["is_default"]]
    assert len(accounts) == 2
    assert len(defaults) == 1  # exactly one default survives
    assert defaults[0]["label"] == "second"


@pytest.mark.asyncio
async def test_duplicate_party_rejected(client, admin_token):
    await _seed_usd()
    h = {"Authorization": f"Bearer {admin_token}"}
    await _create_party(client, h)

    r = await client.post(
        "/api/v1/parties",
        json={"party_type": "supplier", "code": "SCDB", "name": "Dup"},
        headers=h,
    )
    assert r.status_code == 409, r.json()


@pytest.mark.asyncio
async def test_po_links_supplier_party(client, admin_token):
    await _seed_usd()
    h = {"Authorization": f"Bearer {admin_token}"}
    pid = (await _create_party(client, h))["id"]

    r = await client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": "PO-PARTY-1",
            "po_date": "2026-01-10",
            "supplier_party_id": pid,
            "product_description": "Soft drinks",
            "quantity": "100",
            "quantity_unit": "trays",
            "total_value": "10000.00",
            "currency": "USD",
        },
        headers=h,
    )
    assert r.status_code == 200, r.json()

    async with TestSession() as db:
        po = (
            await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-PARTY-1"))
        ).scalar_one()
    assert str(po.supplier_party_id) == pid


@pytest.mark.asyncio
async def test_po_rejects_non_supplier_and_unknown_party(client, admin_token):
    await _seed_usd()
    h = {"Authorization": f"Bearer {admin_token}"}
    haulier = await _create_party(
        client, h, party_type="haulier", code="HAUL-1", name="Fast Haulage"
    )

    base = {
        "po_date": "2026-01-10",
        "product_description": "Soft drinks",
        "quantity": "100",
        "quantity_unit": "trays",
        "total_value": "10000.00",
        "currency": "USD",
    }

    # A non-SUPPLIER party is rejected.
    r = await client.post(
        "/api/v1/purchase-orders",
        json={**base, "po_number": "PO-BAD-1", "supplier_party_id": haulier["id"]},
        headers=h,
    )
    assert r.status_code == 400, r.json()

    # An unknown party id is rejected.
    r = await client.post(
        "/api/v1/purchase-orders",
        json={**base, "po_number": "PO-BAD-2", "supplier_party_id": str(uuid.uuid4())},
        headers=h,
    )
    assert r.status_code == 400, r.json()


@pytest.mark.asyncio
async def test_free_zone_watch_flags_uae_counterparty(client, admin_token):
    await _seed_usd()
    await _seed_free_zone_entity()
    h = {"Authorization": f"Bearer {admin_token}"}

    await _create_party(
        client,
        h,
        party_type="freight_forwarder",
        code="FF-DXB",
        name="Dubai Freight Co",
        country="United Arab Emirates",
    )
    await _create_party(client, h)  # SCDB / Morocco — must NOT be flagged

    r = await client.get("/api/v1/parties/free-zone-watch", headers=h)
    assert r.status_code == 200, r.json()
    flagged = r.json()
    assert len(flagged) == 1
    assert flagged[0]["code"] == "FF-DXB"
    assert flagged[0]["country"] == "United Arab Emirates"
    assert "Free Zone" in flagged[0]["reason"]


@pytest.mark.asyncio
async def test_free_zone_watch_empty_without_free_zone_entity(client, admin_token):
    await _seed_usd()
    h = {"Authorization": f"Bearer {admin_token}"}
    # A UAE counterparty exists, but no UAE Free-Zone trading entity → nothing to watch.
    await _create_party(
        client,
        h,
        code="FF-DXB",
        party_type="freight_forwarder",
        name="Dubai Freight Co",
        country="United Arab Emirates",
    )

    r = await client.get("/api/v1/parties/free-zone-watch", headers=h)
    assert r.status_code == 200
    assert r.json() == []
