"""Unit tests for SupplierPaymentService — threshold and transition logic.

The interesting piece is `_maybe_advance_booking`: given a booking_id,
compute (sum of linked invoices) and (sum of confirmed supplier payments)
and only call BookingService.transition_status when the threshold is met.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import BookingStatus
from app.services.supplier_payment_service import SupplierPaymentService


def _scalar_result(value):
    m = MagicMock()
    m.scalar.return_value = value
    return m


@pytest.mark.asyncio
async def test_no_advance_when_underpaid():
    """Cumulative paid < cumulative invoiced → no transition."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.side_effect = [
        _scalar_result(Decimal("1000.00")),  # invoice sum
        _scalar_result(Decimal("500.00")),  # paid sum
    ]

    with (
        patch("app.services.supplier_payment_service.BookingService.get") as mock_get,
        patch(
            "app.services.supplier_payment_service.BookingService.transition_status"
        ) as mock_trans,
    ):
        await SupplierPaymentService._maybe_advance_booking(db, uuid.uuid4(), MagicMock(), None)

    mock_get.assert_not_called()
    mock_trans.assert_not_called()


@pytest.mark.asyncio
async def test_advance_when_fully_paid():
    """Paid >= invoiced and booking still at INVOICE_RECEIVED → transition fires."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.side_effect = [
        _scalar_result(Decimal("1000.00")),  # invoice sum
        _scalar_result(Decimal("1000.00")),  # paid sum
    ]

    booking_mock = MagicMock()
    booking_mock.status = BookingStatus.INVOICE_RECEIVED

    with (
        patch(
            "app.services.supplier_payment_service.BookingService.get", return_value=booking_mock
        ),
        patch(
            "app.services.supplier_payment_service.BookingService.transition_status"
        ) as mock_trans,
        patch("app.services.supplier_payment_service.NotificationService.notify_booking_roles"),
    ):
        await SupplierPaymentService._maybe_advance_booking(db, uuid.uuid4(), MagicMock(), None)

    mock_trans.assert_awaited_once()
    args = mock_trans.call_args
    assert args[0][2] == BookingStatus.PAYMENT_CONFIRMED


@pytest.mark.asyncio
async def test_no_advance_when_booking_already_confirmed():
    """Booking already past INVOICE_RECEIVED → no double-fire even if threshold met."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.side_effect = [
        _scalar_result(Decimal("1000.00")),
        _scalar_result(Decimal("1000.00")),
    ]

    booking_mock = MagicMock()
    booking_mock.status = BookingStatus.PAYMENT_CONFIRMED  # already advanced

    with (
        patch(
            "app.services.supplier_payment_service.BookingService.get", return_value=booking_mock
        ),
        patch(
            "app.services.supplier_payment_service.BookingService.transition_status"
        ) as mock_trans,
        patch("app.services.supplier_payment_service.NotificationService.notify_booking_roles"),
    ):
        await SupplierPaymentService._maybe_advance_booking(db, uuid.uuid4(), MagicMock(), None)

    mock_trans.assert_not_called()


@pytest.mark.asyncio
async def test_no_advance_when_no_invoices():
    """Total invoiced = 0 (no linked invoices) → no transition attempted."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.side_effect = [_scalar_result(Decimal("0"))]

    with (
        patch("app.services.supplier_payment_service.BookingService.get") as mock_get,
        patch(
            "app.services.supplier_payment_service.BookingService.transition_status"
        ) as mock_trans,
    ):
        await SupplierPaymentService._maybe_advance_booking(db, uuid.uuid4(), MagicMock(), None)

    mock_get.assert_not_called()
    mock_trans.assert_not_called()
