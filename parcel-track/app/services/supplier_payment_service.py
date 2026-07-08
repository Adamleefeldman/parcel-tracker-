"""Supplier payment service.

Adds outbound USD payments against a supplier Invoice and triggers the
BookingStatus.PAYMENT_CONFIRMED transition on every booking the payment's
PO is linked to (once cumulative paid covers the linked invoices' total).

Why per-Invoice (not per-Booking)? Multi-PO bookings have one Invoice per
PO; each Invoice has its own payment trail. Summing at the Booking level
is the precondition's job — it walks the BookingPO → PO → Invoice →
SupplierPayments chain when checking PAYMENT_CONFIRMED.
"""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import BookingStatus, NotificationType, PaymentStatus, UserRole
from app.db.models import (
    BookingPurchaseOrder,
    Invoice,
    PurchaseOrder,
    SupplierPayment,
    User,
)
from app.middleware.auth import financial_fields_allowed
from app.schemas.pagination import PaginationParams, paginate
from app.schemas.schemas import SupplierPaymentCreate, SupplierPaymentOut
from app.services.booking_service import BookingService
from app.services.fx_service import FxService
from app.services.notification_service import NotificationService


class SupplierPaymentService:
    @staticmethod
    async def add(
        db: AsyncSession,
        invoice_id: uuid.UUID,
        body: SupplierPaymentCreate,
        actor: User,
        client_ip: str | None,
    ) -> SupplierPayment:
        # Confirm the invoice exists and pre-load its PO/booking chain so
        # the post-write transition logic doesn't have to re-query.
        result = await db.execute(
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .options(
                selectinload(Invoice.purchase_order)
                .selectinload(PurchaseOrder.booking_links)
                .selectinload(BookingPurchaseOrder.booking)
            )
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(404, "Invoice not found")

        payment = SupplierPayment(
            invoice_id=invoice_id,
            status=PaymentStatus.CONFIRMED,
            **body.model_dump(),
        )
        payment.fx_rate_to_usd, payment.amount_usd = await FxService.capture_usd(
            db, payment.amount, payment.currency
        )
        db.add(payment)
        await db.flush()

        # For each booking this invoice's PO is linked to, check whether
        # cumulative supplier payments now cover all linked invoices' total.
        # If so and the booking is still at INVOICE_RECEIVED, advance it.
        po = invoice.purchase_order
        for link in po.booking_links:
            booking = link.booking
            if booking.status != BookingStatus.INVOICE_RECEIVED:
                continue
            await SupplierPaymentService._maybe_advance_booking(db, booking.id, actor, client_ip)

        return payment

    @staticmethod
    async def _maybe_advance_booking(
        db: AsyncSession,
        booking_id: uuid.UUID,
        actor: User,
        client_ip: str | None,
    ) -> None:
        """Compute paid-vs-invoiced totals for this booking and, if the
        threshold is met, route the transition through BookingService so
        an AuditLog row gets written."""
        inv_sum_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.value), 0))
            .join(PurchaseOrder, PurchaseOrder.id == Invoice.purchase_order_id)
            .join(
                BookingPurchaseOrder,
                BookingPurchaseOrder.purchase_order_id == PurchaseOrder.id,
            )
            .where(BookingPurchaseOrder.booking_id == booking_id)
        )
        total_invoiced = Decimal(inv_sum_q.scalar() or 0)
        if total_invoiced == 0:
            return

        total_paid_q = await db.execute(
            select(func.coalesce(func.sum(SupplierPayment.amount), 0))
            .join(Invoice, Invoice.id == SupplierPayment.invoice_id)
            .join(PurchaseOrder, PurchaseOrder.id == Invoice.purchase_order_id)
            .join(
                BookingPurchaseOrder,
                BookingPurchaseOrder.purchase_order_id == PurchaseOrder.id,
            )
            .where(
                BookingPurchaseOrder.booking_id == booking_id,
                SupplierPayment.status == PaymentStatus.CONFIRMED,
            )
        )
        total_paid = Decimal(total_paid_q.scalar() or 0)
        if total_paid < total_invoiced:
            return

        booking = await BookingService.get(db, booking_id, actor)
        if booking.status == BookingStatus.INVOICE_RECEIVED:
            await BookingService.transition_status(
                db, booking, BookingStatus.PAYMENT_CONFIRMED, actor, client_ip
            )
            await NotificationService.notify_booking_roles(
                db,
                booking_id,
                NotificationType.PAYMENT_CONFIRMED,
                [UserRole.MOROCCO_AGENT],
            )

    @staticmethod
    async def list(
        db: AsyncSession,
        invoice_id: uuid.UUID,
        actor: User,
        pagination: PaginationParams,
    ) -> dict[str, Any]:
        q = select(SupplierPayment).where(SupplierPayment.invoice_id == invoice_id)
        page = await paginate(db, q, pagination)
        show = financial_fields_allowed(actor)
        page["items"] = [
            BookingService.mask_financials(SupplierPaymentOut.model_validate(p).model_dump(), show)
            for p in page["items"]
        ]
        return page
