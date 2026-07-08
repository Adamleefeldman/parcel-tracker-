"""Integration: Pillar 1c money USD-capture wiring across the transaction services.

Exercises the real route -> service -> FxService.capture_usd path on a real (SQLite)
DB. USD transactions capture at rate 1 with no fx_rates row (short-circuit); other
currencies capture from a seeded rate; unknown currencies leave the columns NULL.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import (
    Container,
    CurrencyRef,
    CustomerPayment,
    FxRate,
    Invoice,
    PurchaseOrder,
    SupplierPayment,
)
from tests.integration.conftest import TestSession, advance_to


async def _seed_rate(quote: str, rate: str) -> None:
    """Seed the currencies rows (create_all builds the table but not the migration
    seed) plus one USD-base fx_rate, so rate_to_usd(quote) resolves."""
    async with TestSession() as db:
        for code, is_base in (("USD", True), (quote, False)):
            db.add(CurrencyRef(code=code, name=code, is_base=is_base))
        db.add(
            FxRate(
                base_code="USD",
                quote_code=quote,
                rate=Decimal(rate),
                as_of=datetime(2026, 1, 1, tzinfo=UTC),
                source="manual",
            )
        )
        await db.commit()


def _po_body(po_number: str, currency: str, total: str) -> dict:
    return {
        "po_number": po_number,
        "po_date": "2026-01-10",
        "product_description": "Tiles",
        "quantity": "10",
        "quantity_unit": "boxes",
        "total_value": total,
        "currency": currency,
    }


@pytest.mark.asyncio
async def test_usd_flow_captures_rate_one(client, admin_token):
    """PO + Invoice + SupplierPayment are all USD in advance_to → captured at rate 1
    with NO seeded rate (USD short-circuits)."""
    h = {"Authorization": f"Bearer {admin_token}"}
    await advance_to(client, h, "payment_confirmed", ref="FXC-USD")

    async with TestSession() as db:
        po = (
            await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-FXC-USD"))
        ).scalar_one()
        inv = (
            await db.execute(select(Invoice).where(Invoice.invoice_number == "INV-FXC-USD"))
        ).scalar_one()
        pay = (await db.execute(select(SupplierPayment))).scalar_one()

    for row, amount in ((po, "10000.00"), (inv, "10000.00"), (pay, "10000.00")):
        assert row.fx_rate_to_usd == Decimal("1")
        assert row.amount_usd == Decimal(amount)


@pytest.mark.asyncio
async def test_gbp_po_captures_from_rate(client, admin_token):
    await _seed_rate("GBP", "0.80")  # 1 USD = 0.80 GBP
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.post(
        "/api/v1/purchase-orders", json=_po_body("PO-FXC-GBP", "GBP", "1000.00"), headers=h
    )
    assert r.status_code == 200, r.json()

    async with TestSession() as db:
        po = (
            await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-FXC-GBP"))
        ).scalar_one()

    # £1 = 1/0.80 = $1.25; £1000 = $1250.00.
    assert po.fx_rate_to_usd == Decimal("1.25000000")
    assert po.amount_usd == Decimal("1250.00")


@pytest.mark.asyncio
async def test_no_rate_leaves_columns_null(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.post(
        "/api/v1/purchase-orders", json=_po_body("PO-FXC-EUR", "EUR", "1000.00"), headers=h
    )
    assert r.status_code == 200, r.json()

    async with TestSession() as db:
        po = (
            await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-FXC-EUR"))
        ).scalar_one()

    assert po.fx_rate_to_usd is None
    assert po.amount_usd is None


@pytest.mark.asyncio
async def test_container_sale_and_customer_payment_capture(client, admin_token):
    await _seed_rate("GBP", "0.80")
    h = {"Authorization": f"Bearer {admin_token}"}
    bid, ctx = await advance_to(client, h, "bl_issued", ref="FXC-CTN")
    cid = ctx["container_ids"][0]

    # Container sale price (GBP) → captured on update_sale.
    r = await client.patch(
        f"/api/v1/bookings/{bid}/containers/{cid}/sale",
        json={"sale_price_total": "2000.00", "sale_currency": "GBP"},
        headers=h,
    )
    assert r.status_code == 200, r.json()

    # Customer payment (implicit GBP) → captured on add.
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
        container = (
            await db.execute(select(Container).where(Container.id == uuid.UUID(cid)))
        ).scalar_one()
        payment = (
            await db.execute(
                select(CustomerPayment).where(CustomerPayment.container_id == uuid.UUID(cid))
            )
        ).scalar_one()

    # GBP 2000 x 1.25 = USD 2500.00; GBP 500 x 1.25 = USD 625.00.
    assert container.fx_rate_to_usd == Decimal("1.25000000")
    assert container.amount_usd == Decimal("2500.00")
    assert payment.fx_rate_to_usd == Decimal("1.25000000")
    assert payment.amount_usd == Decimal("625.00")
