"""Integration: Pillar 2 legal-entity tagging across the transaction services.

Exercises the real route -> service path on a real (SQLite) DB. With a default
LegalEntity seeded, every new money/shipment row (booking, PO, invoice, supplier
payment, container, customer payment) is stamped with that entity's id. With no
default seeded, tagging is a graceful no-op (the column is nullable).
"""

import uuid

import pytest
from sqlalchemy import select

from app.db.models import (
    Booking,
    Container,
    CurrencyRef,
    CustomerPayment,
    Invoice,
    LegalEntity,
    PurchaseOrder,
    SupplierPayment,
)
from tests.integration.conftest import TestSession, advance_to


async def _seed_default_entity() -> uuid.UUID:
    """Seed the USD currency (the base_currency_code FK target) + the default
    legal entity. create_all builds the tables but not the migration seed, so
    tests that need the default row insert it directly."""
    async with TestSession() as db:
        db.add(CurrencyRef(code="USD", name="US Dollar", is_base=True))
        entity = LegalEntity(
            code="FMCG_HUB",
            legal_name="WT Trading LLC",
            display_name="The FMCG Hub",
            base_currency_code="USD",
            is_default=True,
        )
        db.add(entity)
        await db.commit()
        return entity.id


@pytest.mark.asyncio
async def test_transactions_tagged_with_default_entity(client, admin_token):
    entity_id = await _seed_default_entity()
    h = {"Authorization": f"Bearer {admin_token}"}

    # Drives booking -> PO -> invoice -> supplier payment -> BL -> containers.
    bid, ctx = await advance_to(client, h, "bl_issued", ref="LE-TAG")
    cid = ctx["container_ids"][0]

    # Customer payment against the first container (the 6th tagged create-site).
    r = await client.post(
        f"/api/v1/bookings/{bid}/containers/{cid}/customer-payments",
        json={
            "payment_date": "2026-02-20",
            "method": "transfer",
            "amount_received": "500.00",
            "tranche_index": 1,
        },
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, r.json()

    async with TestSession() as db:
        booking = (
            await db.execute(select(Booking).where(Booking.id == uuid.UUID(bid)))
        ).scalar_one()
        po = (await db.execute(select(PurchaseOrder))).scalar_one()
        invoice = (await db.execute(select(Invoice))).scalar_one()
        supplier_payment = (await db.execute(select(SupplierPayment))).scalar_one()
        container = (
            await db.execute(select(Container).where(Container.id == uuid.UUID(cid)))
        ).scalar_one()
        customer_payment = (await db.execute(select(CustomerPayment))).scalar_one()

    for row in (booking, po, invoice, supplier_payment, container, customer_payment):
        assert row.legal_entity_id == entity_id, f"{type(row).__name__} was not tagged"


@pytest.mark.asyncio
async def test_untagged_when_no_default_entity(client, admin_token):
    """Without a seeded default entity, tagging is a graceful no-op (nullable)."""
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": "PO-LE-NONE",
            "po_date": "2026-01-10",
            "product_description": "Tiles",
            "quantity": "10",
            "quantity_unit": "boxes",
            "total_value": "1000.00",
            "currency": "USD",
        },
        headers=h,
    )
    assert r.status_code == 200, r.json()

    async with TestSession() as db:
        po = (
            await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-LE-NONE"))
        ).scalar_one()

    assert po.legal_entity_id is None
