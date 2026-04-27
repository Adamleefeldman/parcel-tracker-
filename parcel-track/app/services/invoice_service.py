"""Invoice service — create, acknowledge discrepancy, and read invoices."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InvoiceStatus, ShipmentStatus
from app.core.exceptions import handle_integrity_error
from app.db.models import Invoice, PurchaseOrder, User
from app.middleware.auth import financial_fields_allowed
from app.schemas.schemas import InvoiceCreate, InvoiceOut
from app.services.shipment_service import ShipmentService


class InvoiceService:
    @staticmethod
    def _variance_exceeded(invoice_value: float, po_value: float) -> bool:
        """Return True when invoice/PO value differ by more than 2%."""
        return abs(invoice_value - po_value) / po_value > 0.02


    @staticmethod
    async def create(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        body: InvoiceCreate,
        actor: User,
        client_ip: str | None,
    ) -> Invoice:
        po_result = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.shipment_id == shipment_id)
        )
        po = po_result.scalar_one_or_none()
        if po and body.invoice_date < po.po_date:
            raise HTTPException(400, "Invoice date must be on or after PO date")

        async with handle_integrity_error("An invoice with this invoice number already exists"):
            invoice = Invoice(
                shipment_id=shipment_id, status=InvoiceStatus.RECEIVED, **body.model_dump()
            )
            db.add(invoice)
            await db.flush()

        if po and InvoiceService._variance_exceeded(float(body.value), float(po.total_value)):
            invoice.status = InvoiceStatus.DISCREPANCY

        shipment = await ShipmentService.get(db, shipment_id, actor)
        await ShipmentService.transition_status(
            db, shipment, ShipmentStatus.INVOICE_RECEIVED, actor, client_ip
        )

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
        shipment_id: uuid.UUID,
        actor: User,
    ) -> dict:
        result = await db.execute(select(Invoice).where(Invoice.shipment_id == shipment_id))
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(404, "Invoice not found")

        data = InvoiceOut.model_validate(invoice).model_dump()
        return ShipmentService.mask_financials(data, financial_fields_allowed(actor))
