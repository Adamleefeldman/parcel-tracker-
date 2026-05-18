"""
BookingService owns all state machine logic.
No route handler or other service should write booking.status directly —
all transitions flow through transition_status() which enforces preconditions.

A Booking is the shipping-line operational unit. It aggregates one or more
PurchaseOrders via the BookingPurchaseOrder junction (e.g. DP World booking
2601008 covers PO-2026-04 and PO-2026-05). Per-PO checks (PO submitted,
Invoice received, supplier paid) iterate over every PO linked to the Booking.
"""

import json
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    BookingStatus,
    ContainerLifecycleStatus,
    ContainerStatus,
    InvoiceStatus,
    PaymentStatus,
    POStatus,
)
from app.db.models import (
    AuditLog,
    BillOfLading,
    Booking,
    BookingPurchaseOrder,
    BookingUser,
    Container,
    DeliveryContainer,
    DeliveryPoint,
    Invoice,
    PurchaseOrder,
    SupplierPayment,
    User,
    Vessel,
)

# ── Allowed state transitions ─────────────────────────────────────────────────

VALID_TRANSITIONS: dict[BookingStatus, list[BookingStatus]] = {
    BookingStatus.DRAFT: [BookingStatus.PO_SUBMITTED],
    BookingStatus.PO_SUBMITTED: [BookingStatus.INVOICE_RECEIVED],
    BookingStatus.INVOICE_RECEIVED: [BookingStatus.PAYMENT_CONFIRMED],
    BookingStatus.PAYMENT_CONFIRMED: [BookingStatus.BL_ISSUED],
    BookingStatus.BL_ISSUED: [BookingStatus.IN_TRANSIT],
    BookingStatus.IN_TRANSIT: [BookingStatus.CLEARED],
    BookingStatus.CLEARED: [BookingStatus.COMPLETE],
    BookingStatus.COMPLETE: [],  # terminal
}


class BookingService:
    @staticmethod
    async def create(db: AsyncSession, reference: str, actor: User) -> Booking:
        # Ensure unique reference
        exists = await db.execute(select(Booking).where(Booking.reference == reference))
        if exists.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Booking reference '{reference}' already exists",
            )

        booking = Booking(reference=reference, created_by=actor.id)
        db.add(booking)
        await db.flush()

        # Admin is automatically a member
        db.add(BookingUser(booking_id=booking.id, user_id=actor.id))
        await db.flush()

        return booking

    @staticmethod
    async def get(db: AsyncSession, booking_id: uuid.UUID, actor: User) -> Booking:
        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(
                # Booking → POs → Invoice → SupplierPayments
                # (single chain that covers the financial view at booking detail).
                selectinload(Booking.purchase_order_links)
                .selectinload(BookingPurchaseOrder.purchase_order)
                .selectinload(PurchaseOrder.invoice)
                .selectinload(Invoice.supplier_payments),
                # Load BL → containers → broker + end_company so the response
                # serialiser can populate the P0.2 sale-side fields without
                # triggering lazy loads in async context.
                selectinload(Booking.bill_of_lading)
                .selectinload(BillOfLading.containers)
                .selectinload(Container.broker),
                selectinload(Booking.bill_of_lading)
                .selectinload(BillOfLading.containers)
                .selectinload(Container.end_company),
                selectinload(Booking.bill_of_lading)
                .selectinload(BillOfLading.vessel)
                .selectinload(Vessel.updates),
                selectinload(Booking.clearing_docs),
                selectinload(Booking.delivery_points).selectinload(DeliveryPoint.schedule),
                # Delivery-point-level broker / end_company (P0.5) so the
                # detail view can show who's receiving each drop.
                selectinload(Booking.delivery_points).selectinload(DeliveryPoint.broker),
                selectinload(Booking.delivery_points).selectinload(DeliveryPoint.end_company),
                # Delivery-point containers also need broker / end_company eager-loaded.
                selectinload(Booking.delivery_points)
                .selectinload(DeliveryPoint.container_assignments)
                .selectinload(DeliveryContainer.container)
                .selectinload(Container.broker),
                selectinload(Booking.delivery_points)
                .selectinload(DeliveryPoint.container_assignments)
                .selectinload(DeliveryContainer.container)
                .selectinload(Container.end_company),
            )
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        return booking

    @staticmethod
    async def update(db: AsyncSession, booking_id: uuid.UUID, data: dict, actor: User) -> Booking:
        result = await db.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        for key, value in data.items():
            if value is not None:
                setattr(booking, key, value)

        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking reference or booking number already exists",
            ) from None

        await db.refresh(booking)
        return booking

    @staticmethod
    async def attach_purchase_order(
        db: AsyncSession,
        booking_id: uuid.UUID,
        purchase_order_id: uuid.UUID,
    ) -> BookingPurchaseOrder:
        """
        Attach an existing PurchaseOrder to a Booking. Either side missing →
        404; link already exists → 409.
        """
        b = await db.execute(select(Booking).where(Booking.id == booking_id))
        if not b.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        p = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == purchase_order_id))
        if not p.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found"
            )

        existing = await db.execute(
            select(BookingPurchaseOrder).where(
                BookingPurchaseOrder.booking_id == booking_id,
                BookingPurchaseOrder.purchase_order_id == purchase_order_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Purchase order is already linked to this booking",
            )

        link = BookingPurchaseOrder(booking_id=booking_id, purchase_order_id=purchase_order_id)
        db.add(link)
        await db.flush()
        return link

    @staticmethod
    async def transition_status(
        db: AsyncSession,
        booking: Booking,
        new_status: BookingStatus,
        actor: User,
        ip: str | None = None,
    ) -> Booking:
        """
        Central state gate. Checks:
        1. Transition is in VALID_TRANSITIONS
        2. All preconditions for the target state are met
        Then writes the new status and logs the change.
        """
        current = booking.status
        if new_status not in VALID_TRANSITIONS.get(current, []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition from '{current}' to '{new_status}'",
            )

        await BookingService._check_preconditions(db, booking, new_status)

        old_status = booking.status
        booking.status = new_status

        db.add(
            AuditLog(
                booking_id=booking.id,
                actor_id=actor.id,
                action="booking.status_changed",
                entity_type="booking",
                entity_id=booking.id,
                old_value=json.dumps({"status": old_status.value}),
                new_value=json.dumps({"status": new_status.value}),
                ip_address=ip,
            )
        )

        return booking

    @staticmethod
    async def _check_preconditions(
        db: AsyncSession,
        booking: Booking,
        target: BookingStatus,
    ) -> None:
        """
        Raises HTTPException if preconditions for target state are not met.
        Per-PO checks iterate over every PO linked to the Booking via the
        BookingPurchaseOrder junction.
        """

        if target == BookingStatus.PO_SUBMITTED:
            # At least one linked PO must be submitted with its document uploaded.
            # Booking advances on first submitted PO; further POs can be attached after.
            submitted = await db.execute(
                select(PurchaseOrder)
                .join(
                    BookingPurchaseOrder,
                    BookingPurchaseOrder.purchase_order_id == PurchaseOrder.id,
                )
                .where(
                    BookingPurchaseOrder.booking_id == booking.id,
                    PurchaseOrder.status == POStatus.SUBMITTED,
                )
            )
            if not submitted.scalars().first():
                raise HTTPException(
                    400, "At least one submitted PO must be linked before proceeding"
                )

        elif target == BookingStatus.INVOICE_RECEIVED:
            # Every linked PO must have an Invoice received (or reconciled),
            # and no unacknowledged discrepancies.
            pos = await db.execute(
                select(PurchaseOrder)
                .join(
                    BookingPurchaseOrder,
                    BookingPurchaseOrder.purchase_order_id == PurchaseOrder.id,
                )
                .where(BookingPurchaseOrder.booking_id == booking.id)
                .options(selectinload(PurchaseOrder.invoice))
            )
            po_list = pos.scalars().all()
            if not po_list:
                raise HTTPException(400, "No linked POs found")
            for po in po_list:
                invoice = po.invoice
                if not invoice:
                    raise HTTPException(
                        400,
                        f"Invoice for PO {po.po_number} must be uploaded before proceeding",
                    )
                if invoice.status == InvoiceStatus.DISCREPANCY:
                    if not invoice.discrepancy_acknowledged:
                        raise HTTPException(
                            400,
                            f"Invoice discrepancy on PO {po.po_number} must be acknowledged",
                        )
                elif invoice.status not in (
                    InvoiceStatus.RECEIVED,
                    InvoiceStatus.RECONCILED,
                ):
                    raise HTTPException(
                        400,
                        f"Invoice for PO {po.po_number} must be uploaded before proceeding",
                    )

        elif target == BookingStatus.PAYMENT_CONFIRMED:
            # Sum the invoice values across every PO linked to this booking,
            # then sum the confirmed SupplierPayments against those invoices.
            # Both queries walk the BookingPurchaseOrder ↔ PurchaseOrder ↔
            # Invoice chain so multi-PO bookings reconcile naturally.
            invoice_sum = await db.execute(
                select(func.coalesce(func.sum(Invoice.value), 0))
                .join(PurchaseOrder, PurchaseOrder.id == Invoice.purchase_order_id)
                .join(
                    BookingPurchaseOrder,
                    BookingPurchaseOrder.purchase_order_id == PurchaseOrder.id,
                )
                .where(BookingPurchaseOrder.booking_id == booking.id)
            )
            total_invoiced = Decimal(invoice_sum.scalar() or 0)
            if total_invoiced == 0:
                raise HTTPException(400, "No invoices found across linked POs")

            total_paid_q = await db.execute(
                select(func.coalesce(func.sum(SupplierPayment.amount), 0))
                .join(Invoice, Invoice.id == SupplierPayment.invoice_id)
                .join(PurchaseOrder, PurchaseOrder.id == Invoice.purchase_order_id)
                .join(
                    BookingPurchaseOrder,
                    BookingPurchaseOrder.purchase_order_id == PurchaseOrder.id,
                )
                .where(
                    BookingPurchaseOrder.booking_id == booking.id,
                    SupplierPayment.status == PaymentStatus.CONFIRMED,
                )
            )
            paid = Decimal(total_paid_q.scalar() or 0)
            if paid < total_invoiced:
                raise HTTPException(
                    400,
                    f"Payments ({paid}) do not cover total invoice value ({total_invoiced})",
                )

        elif target == BookingStatus.BL_ISSUED:
            bl = await db.execute(select(BillOfLading).where(BillOfLading.booking_id == booking.id))
            if not bl.scalar_one_or_none():
                raise HTTPException(400, "Bill of lading must be uploaded before proceeding")

        elif target == BookingStatus.IN_TRANSIT:
            vessel = await db.execute(
                select(Vessel)
                .join(BillOfLading, Vessel.bl_id == BillOfLading.id)
                .where(BillOfLading.booking_id == booking.id)
            )
            v = vessel.scalar_one_or_none()
            if not v or not v.atd:
                raise HTTPException(400, "Vessel actual departure date (ATD) must be confirmed")

        elif target == BookingStatus.CLEARED:
            containers = await db.execute(
                select(Container)
                .join(BillOfLading, Container.bl_id == BillOfLading.id)
                .where(BillOfLading.booking_id == booking.id)
            )
            all_containers = containers.scalars().all()
            if not all_containers:
                raise HTTPException(400, "No containers found for this booking")
            not_cleared = [c for c in all_containers if c.status != ContainerStatus.CLEARED]
            if not_cleared:
                raise HTTPException(
                    400, f"{len(not_cleared)} container(s) not yet cleared through customs"
                )

        elif target == BookingStatus.COMPLETE:
            # COMPLETE = the booking is closed financially as well as
            # operationally. Every container on the booking must have
            # reached BANKED (customer payment received and banked) or be
            # explicitly acknowledged DISPUTED. Old behaviour ("all
            # delivery points delivered") was insufficient — it ignored
            # the customer-side leg entirely.
            containers_q = await db.execute(
                select(Container)
                .join(BillOfLading, Container.bl_id == BillOfLading.id)
                .where(BillOfLading.booking_id == booking.id)
            )
            all_containers = containers_q.scalars().all()
            if not all_containers:
                raise HTTPException(400, "No containers found for this booking")

            terminal = {ContainerLifecycleStatus.BANKED, ContainerLifecycleStatus.CLOSED}
            pending = [
                c
                for c in all_containers
                if c.lifecycle_status not in terminal
                and c.lifecycle_status != ContainerLifecycleStatus.DISPUTED
            ]
            if pending:
                raise HTTPException(
                    400,
                    f"{len(pending)} container(s) not yet banked: "
                    f"{[c.container_number for c in pending]}",
                )

            # Disputed containers must have an acknowledgement (an admin
            # explicitly OK'd them via the dispute-acknowledge route — for
            # now we require dispute_reason be cleared to count as resolved;
            # full acknowledgement flow lands in P2.5).
            unresolved_disputes = [
                c for c in all_containers if c.lifecycle_status == ContainerLifecycleStatus.DISPUTED
            ]
            if unresolved_disputes:
                raise HTTPException(
                    400,
                    f"{len(unresolved_disputes)} container(s) disputed; "
                    "acknowledge before completing.",
                )

    @staticmethod
    def mask_financials(obj: dict, show: bool) -> dict:
        """Strip financial keys from a dict when show=False (non-admin)."""
        if show:
            return obj
        financial_keys = {
            "total_value",
            "value",
            "amount",
            "swift_ref",
            "duty_paid",
            "estimated_duty_vat",
        }
        return {k: (None if k in financial_keys else v) for k, v in obj.items()}
