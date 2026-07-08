"""Invoice service — create, acknowledge discrepancy, and read supplier invoices."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import BookingStatus, InvoiceStatus
from app.core.exceptions import handle_integrity_error
from app.db.models import (
    BookingPurchaseOrder,
    Invoice,
    PurchaseOrder,
    User,
)
from app.middleware.auth import financial_fields_allowed
from app.schemas.schemas import InvoiceCreate, InvoiceOut
from app.services.booking_service import BookingService
from app.services.fx_service import FxService
from app.services.legal_entity_service import LegalEntityService


class InvoiceService:
    @staticmethod
    def _variance_exceeded(invoice_value: float, po_value: float) -> bool:
        """Return True when invoice/PO value differ by more than 2%."""
        return abs(invoice_value - po_value) / po_value > 0.02

    @staticmethod
    async def create(
        db: AsyncSession,
        po_id: uuid.UUID,
        body: InvoiceCreate,
        actor: User,
        client_ip: str | None,
    ) -> Invoice:
        po_result = await db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .options(
                selectinload(PurchaseOrder.booking_links).selectinload(BookingPurchaseOrder.booking)
            )
        )
        po = po_result.scalar_one_or_none()
        if not po:
            raise HTTPException(404, "Purchase order not found")
        if body.invoice_date < po.po_date:
            raise HTTPException(400, "Invoice date must be on or after PO date")

        async with handle_integrity_error("An invoice with this invoice number already exists"):
            invoice = Invoice(
                purchase_order_id=po_id, status=InvoiceStatus.RECEIVED, **body.model_dump()
            )
            invoice.legal_entity_id = (
                invoice.legal_entity_id or await LegalEntityService.default_id(db)
            )
            invoice.fx_rate_to_usd, invoice.amount_usd = await FxService.capture_usd(
                db, invoice.value, invoice.currency
            )
            db.add(invoice)
            await db.flush()

        if InvoiceService._variance_exceeded(float(body.value), float(po.total_value)):
            invoice.status = InvoiceStatus.DISCREPANCY

        # Attempt to advance every linked booking. Outcomes:
        #   - Booking in PO_SUBMITTED and every linked PO has an invoice →
        #     transition to INVOICE_RECEIVED succeeds.
        #   - Booking in PO_SUBMITTED but other linked POs still missing
        #     invoices → precondition raises "Invoice for PO X must be
        #     uploaded"; we swallow that one error so the caller can fill
        #     invoices in any order without the booking-advance noise.
        #   - Booking in any other state (DRAFT, etc.) → state-machine
        #     guard raises "Cannot transition from ..."; that error
        #     bubbles up because it indicates the caller is trying to
        #     skip a step.
        for link in po.booking_links:
            booking = link.booking
            try:
                await BookingService.transition_status(
                    db, booking, BookingStatus.INVOICE_RECEIVED, actor, client_ip
                )
            except HTTPException as exc:
                if (
                    exc.status_code == 400
                    and isinstance(exc.detail, str)
                    and exc.detail.startswith("Invoice for PO ")
                ):
                    continue
                raise

        return invoice

    @staticmethod
    async def acknowledge_discrepancy(
        db: AsyncSession,
        invoice_id: uuid.UUID,
    ) -> None:
        result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(404, "Invoice not found")
        invoice.discrepancy_acknowledged = True

    @staticmethod
    async def get_for_actor(
        db: AsyncSession,
        po_id: uuid.UUID,
        actor: User,
    ) -> dict:
        result = await db.execute(select(Invoice).where(Invoice.purchase_order_id == po_id))
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(404, "Invoice not found")

        data = InvoiceOut.model_validate(invoice).model_dump()
        return BookingService.mask_financials(data, financial_fields_allowed(actor))
