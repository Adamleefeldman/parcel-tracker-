"""Invoice routes (admin-only writes; idempotent create)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InvoiceStatus, ShipmentStatus
from app.core.exceptions import handle_integrity_error
from app.db.database import get_db
from app.db.models import Invoice, PurchaseOrder, User
from app.middleware.auth import (
    financial_fields_allowed,
    get_client_ip,
    require_admin,
    require_shipment_member,
)
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.schemas import InvoiceCreate, InvoiceOut
from app.services.shipment_service import ShipmentService

invoice_router = APIRouter(prefix="/shipments/{shipment_id}/invoice", tags=["invoice"])


@invoice_router.post("", response_model=InvoiceOut)
async def create_invoice(
    shipment_id: uuid.UUID,
    body: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    request: Request = None,
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

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

    if po:
        diff = abs(float(body.value) - float(po.total_value)) / float(po.total_value)
        if diff > 0.02:
            invoice.status = InvoiceStatus.DISCREPANCY

    shipment = await ShipmentService.get(db, shipment_id, actor)
    await ShipmentService.transition_status(
        db, shipment, ShipmentStatus.INVOICE_RECEIVED, actor, get_client_ip(request)
    )

    result = InvoiceOut.model_validate(invoice).model_dump(mode="json")
    await idempotency.store(result)
    return invoice


@invoice_router.patch("/{invoice_id}/acknowledge-discrepancy")
async def acknowledge_discrepancy(
    shipment_id: uuid.UUID,
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    invoice.discrepancy_acknowledged = True
    return {"message": "Discrepancy acknowledged"}


@invoice_router.get("", response_model=InvoiceOut)
async def get_invoice(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    result = await db.execute(select(Invoice).where(Invoice.shipment_id == shipment_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    data = InvoiceOut.model_validate(invoice).model_dump()
    return ShipmentService.mask_financials(data, financial_fields_allowed(actor))
