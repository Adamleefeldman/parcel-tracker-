"""Customer-payment financial-masking tests.

Customer-payment money fields are admin-only. A non-admin booking member may
read the rows (list + aggregate) but every money / bank-detail field must come
back null; non-financial fields (tranche_index, payment_date, method, id,
container_id, created_at, tranche_count) stay visible.

Regression guard for the leak where BookingService.mask_financials' hardcoded
key set did not cover the customer-payment field names, and the aggregate route
never masked at all.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.db.models import CustomerPayment
from app.core.enums import CustomerPaymentMethod

pytestmark = pytest.mark.asyncio


MONEY_FIELDS = (
    "amount_received",
    "variance",
    "expense_courier",
    "expense_bank_charge",
    "banked_total",
    "sender_bank",
    "receiver_bank",
)
AGGREGATE_MONEY_FIELDS = (
    "total_received",
    "total_variance",
    "total_expenses",
    "total_banked",
)


@pytest.fixture
async def seeded_payments(db_session, container):
    """Two tranches against the container with full money + bank detail."""
    rows = [
        CustomerPayment(
            id=uuid.uuid4(),
            container_id=container.id,
            payment_date=date(2026, 5, 1),
            method=CustomerPaymentMethod.TRANSFER,
            amount_received=Decimal("12000.00"),
            variance=Decimal("100.00"),
            expense_courier=Decimal("50.00"),
            expense_bank_charge=Decimal("25.00"),
            banked_total=Decimal("11825.00"),
            sender_bank="Customer Bank plc",
            receiver_bank="WT Trading Bank",
            tranche_index=1,
        ),
        CustomerPayment(
            id=uuid.uuid4(),
            container_id=container.id,
            payment_date=date(2026, 5, 10),
            method=CustomerPaymentMethod.CASH,
            amount_received=Decimal("4000.00"),
            variance=Decimal("0.00"),
            expense_courier=Decimal("0.00"),
            expense_bank_charge=Decimal("0.00"),
            banked_total=Decimal("4000.00"),
            sender_bank="Customer Bank plc",
            receiver_bank="WT Trading Bank",
            tranche_index=2,
        ),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.commit()
    return rows


def _url(booking, container, suffix=""):
    return (
        f"/api/v1/bookings/{booking.id}/containers/{container.id}/customer-payments{suffix}"
    )


async def test_admin_sees_real_amounts_on_list(
    client, auth_headers, booking, container, admin_membership, seeded_payments
):
    resp = await client.get(_url(booking, container), headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    first = items[0]
    assert first["amount_received"] == "12000.00"
    assert first["banked_total"] == "11825.00"
    assert first["sender_bank"] == "Customer Bank plc"
    assert first["tranche_index"] == 1


async def test_admin_sees_real_totals_on_aggregate(
    client, auth_headers, booking, container, admin_membership, seeded_payments
):
    resp = await client.get(_url(booking, container, "/aggregate"), headers=auth_headers)
    assert resp.status_code == 200
    agg = resp.json()
    assert Decimal(str(agg["total_received"])) == Decimal("16000.00")
    assert Decimal(str(agg["total_banked"])) == Decimal("15825.00")
    assert Decimal(str(agg["total_expenses"])) == Decimal("75.00")
    assert agg["tranche_count"] == 2


async def test_non_admin_member_masked_on_list(
    client,
    agent_headers,
    booking,
    container,
    booking_member_agent,
    seeded_payments,
):
    resp = await client.get(_url(booking, container), headers=agent_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    for item in items:
        for field in MONEY_FIELDS:
            assert item[field] is None, f"{field} leaked to non-admin"
        # Non-financial fields stay visible.
        assert item["tranche_index"] in (1, 2)
        assert item["payment_date"] is not None
        assert item["method"] in ("cash", "transfer")
        assert item["id"] is not None
        assert item["container_id"] == str(container.id)
        assert item["created_at"] is not None


async def test_non_admin_member_masked_on_aggregate(
    client,
    agent_headers,
    booking,
    container,
    booking_member_agent,
    seeded_payments,
):
    resp = await client.get(_url(booking, container, "/aggregate"), headers=agent_headers)
    assert resp.status_code == 200
    agg = resp.json()
    for field in AGGREGATE_MONEY_FIELDS:
        assert agg[field] is None, f"{field} leaked to non-admin"
    # tranche_count is not financial — stays visible.
    assert agg["tranche_count"] == 2
