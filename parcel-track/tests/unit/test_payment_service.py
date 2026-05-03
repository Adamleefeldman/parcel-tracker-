"""Unit tests for PaymentService — payment threshold and transition logic."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import ShipmentStatus
from app.services.payment_service import PaymentService


def _make_db(*, invoice_value: Decimal, paid_total: Decimal, shipment_status: ShipmentStatus):
    """Build a minimal AsyncSession mock for PaymentService.add."""
    invoice = MagicMock()
    invoice.value = invoice_value

    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    # First execute: Payment insert (flush only, no return needed)
    # Second execute: Invoice fetch → returns invoice
    # Third execute: SUM of payments → returns paid_total
    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = invoice
    sum_result = MagicMock()
    sum_result.scalar.return_value = paid_total

    db.execute.side_effect = [
        None,  # flush of Payment (execute not called for add/flush)
        inv_result,  # invoice fetch
        sum_result,  # SUM query
    ]
    return db, invoice


@pytest.mark.asyncio
async def test_payment_does_not_transition_when_underpaid():
    invoice_value = Decimal("1000.00")
    paid_so_far = Decimal("500.00")

    actor = MagicMock()
    body = MagicMock()
    body.model_dump.return_value = {}

    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    invoice_mock = MagicMock()
    invoice_mock.value = invoice_value

    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = invoice_mock
    sum_result = MagicMock()
    sum_result.scalar.return_value = paid_so_far

    db.execute.side_effect = [inv_result, sum_result]

    import uuid

    with (
        patch("app.services.payment_service.Payment") as MockPayment,
        patch("app.services.payment_service.ShipmentService.get"),
        patch("app.services.payment_service.ShipmentService.transition_status") as mock_trans,
        patch("app.services.payment_service.NotificationService.notify_shipment_roles"),
    ):
        MockPayment.return_value = MagicMock()
        await PaymentService.add(db, uuid.uuid4(), body, actor, None)

    mock_trans.assert_not_called()


@pytest.mark.asyncio
async def test_payment_transitions_when_fully_paid():
    invoice_value = Decimal("1000.00")
    paid_so_far = Decimal("1000.00")

    actor = MagicMock()
    actor.id = "actor-1"

    body = MagicMock()
    body.model_dump.return_value = {
        "amount": Decimal("1000.00"),
        "payment_date": "2026-01-01",
        "swift_ref": "SW1",
        "payment_method": "WIRE",
    }

    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    invoice_mock = MagicMock()
    invoice_mock.value = invoice_value

    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = invoice_mock
    sum_result = MagicMock()
    sum_result.scalar.return_value = paid_so_far

    db.execute.side_effect = [inv_result, sum_result]

    shipment_mock = MagicMock()
    shipment_mock.status = ShipmentStatus.INVOICE_RECEIVED

    import uuid

    with (
        patch("app.services.payment_service.Payment") as MockPayment,
        patch("app.services.payment_service.ShipmentService.get", return_value=shipment_mock),
        patch("app.services.payment_service.ShipmentService.transition_status") as mock_trans,
        patch("app.services.payment_service.NotificationService.notify_shipment_roles"),
    ):
        MockPayment.return_value = MagicMock()
        await PaymentService.add(db, uuid.uuid4(), body, actor, None)

    mock_trans.assert_awaited_once()
    args = mock_trans.call_args
    assert args[0][2] == ShipmentStatus.PAYMENT_CONFIRMED


@pytest.mark.asyncio
async def test_payment_does_not_double_transition_when_already_confirmed():
    """If shipment is already past INVOICE_RECEIVED, don't trigger again."""
    invoice_value = Decimal("1000.00")
    paid_so_far = Decimal("1000.00")

    actor = MagicMock()
    body = MagicMock()
    body.model_dump.return_value = {}

    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    invoice_mock = MagicMock()
    invoice_mock.value = invoice_value

    inv_result = MagicMock()
    inv_result.scalar_one_or_none.return_value = invoice_mock
    sum_result = MagicMock()
    sum_result.scalar.return_value = paid_so_far

    db.execute.side_effect = [inv_result, sum_result]

    shipment_mock = MagicMock()
    shipment_mock.status = ShipmentStatus.PAYMENT_CONFIRMED  # already advanced

    import uuid

    with (
        patch("app.services.payment_service.Payment") as MockPayment,
        patch("app.services.payment_service.ShipmentService.get", return_value=shipment_mock),
        patch("app.services.payment_service.ShipmentService.transition_status") as mock_trans,
        patch("app.services.payment_service.NotificationService.notify_shipment_roles"),
    ):
        MockPayment.return_value = MagicMock()
        await PaymentService.add(db, uuid.uuid4(), body, actor, None)

    mock_trans.assert_not_called()
