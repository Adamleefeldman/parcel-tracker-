"""Invoice routes (admin-only writes; idempotent create)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, require_admin, require_shipment_member
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.schemas import InvoiceCreate, InvoiceOut
from app.services.invoice_service import InvoiceService

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

    invoice = await InvoiceService.create(db, shipment_id, body, actor, get_client_ip(request))
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
    await InvoiceService.acknowledge_discrepancy(db, invoice_id)
    return {"message": "Discrepancy acknowledged"}


@invoice_router.get("")
async def get_invoice(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    return await InvoiceService.get_for_actor(db, shipment_id, actor)
