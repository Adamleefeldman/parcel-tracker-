"""Purchase Order service — create, submit, and read POs."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import BookingStatus, DocumentEntityType, NotificationType, POStatus, UserRole
from app.core.exceptions import handle_integrity_error
from app.db.models import (
    BookingPurchaseOrder,
    Document,
    PurchaseOrder,
    User,
)
from app.middleware.auth import financial_fields_allowed
from app.schemas.schemas import POCreate, POOut
from app.services.booking_service import BookingService
from app.services.notification_service import NotificationService


class PoService:
    @staticmethod
    async def create(
        db: AsyncSession,
        body: POCreate,
    ) -> PurchaseOrder:
        """
        Create a standalone PurchaseOrder. The PO is not yet attached to any
        Booking — that happens via POST /bookings/{id}/purchase-orders.
        """
        async with handle_integrity_error("A PO with this PO number already exists"):
            po = PurchaseOrder(**body.model_dump())
            db.add(po)
            await db.flush()

        # Re-fetch with the invoice relationship loaded so the POOut response
        # schema can read po.invoice without tripping lazy-loading in async mode.
        result = await db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po.id)
            .options(selectinload(PurchaseOrder.invoice))
        )
        return result.scalar_one()

    @staticmethod
    async def submit(
        db: AsyncSession,
        po_id: uuid.UUID,
        actor: User,
        client_ip: str | None,
    ) -> None:
        """
        Submit a PurchaseOrder. Marks the PO as SUBMITTED and, for every Booking
        currently linked to this PO that's still in DRAFT, advances that booking
        to PO_SUBMITTED. (Most POs link to exactly one booking, but the join
        table permits N.)
        """
        result = await db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .options(
                selectinload(PurchaseOrder.booking_links).selectinload(BookingPurchaseOrder.booking)
            )
        )
        po = result.scalar_one_or_none()
        if not po:
            raise HTTPException(404, "PO not found")

        doc = await db.execute(
            select(Document).where(
                Document.entity_type == DocumentEntityType.PURCHASE_ORDER,
                Document.entity_id == po_id,
            )
        )
        if not doc.scalar_one_or_none():
            raise HTTPException(400, "Document must be uploaded before submitting PO")

        po.status = POStatus.SUBMITTED

        # Advance every booking this PO is linked to. We always attempt the
        # transition: if the booking is already past DRAFT (e.g. a second
        # PO joins an already-advanced booking, or a caller re-submits the
        # same PO), the state-machine guard surfaces the violation as a
        # 400 — which is the right answer. If the caller really wanted to
        # add another PO to an in-flight booking, they should attach the
        # PO without re-running submit.
        for link in po.booking_links:
            booking = link.booking
            await BookingService.transition_status(
                db, booking, BookingStatus.PO_SUBMITTED, actor, client_ip
            )
            await NotificationService.notify_booking_roles(
                db,
                booking.id,
                NotificationType.PO_SUBMITTED,
                [UserRole.ADMIN, UserRole.MOROCCO_AGENT],
            )

    @staticmethod
    async def get_for_actor(
        db: AsyncSession,
        po_id: uuid.UUID,
        actor: User,
    ) -> dict:
        result = await db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .options(selectinload(PurchaseOrder.invoice))
        )
        po = result.scalar_one_or_none()
        if not po:
            raise HTTPException(404, "PO not found")

        data = POOut.model_validate(
            {
                "id": po.id,
                "po_number": po.po_number,
                "po_date": po.po_date,
                "product_description": po.product_description,
                "quantity": po.quantity,
                "quantity_unit": po.quantity_unit,
                "total_value": po.total_value,
                "currency": po.currency.value,
                "status": po.status.value,
                "notes": po.notes,
                "invoice": (
                    {
                        "id": po.invoice.id,
                        "invoice_number": po.invoice.invoice_number,
                        "invoice_date": po.invoice.invoice_date,
                        "value": po.invoice.value,
                        "currency": po.invoice.currency.value,
                        "payment_terms": po.invoice.payment_terms,
                        "due_date": po.invoice.due_date,
                        "status": po.invoice.status.value,
                        "discrepancy_acknowledged": po.invoice.discrepancy_acknowledged,
                        "created_at": po.invoice.created_at,
                    }
                    if po.invoice
                    else None
                ),
                "created_at": po.created_at,
            }
        ).model_dump()
        return BookingService.mask_financials(data, financial_fields_allowed(actor))
