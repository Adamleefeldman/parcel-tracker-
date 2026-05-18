"""Invoice routes (admin-only writes; idempotent create).

Invoices are the supplier's Commercial Invoice — one per PurchaseOrder. They
nest under /purchase-orders/{po_id}/invoice. The customer-side outbound
invoice is a separate concern (deferred to a later phase).
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, get_current_user, require_admin
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.schemas import InvoiceCreate, InvoiceOut
from app.services.invoice_service import InvoiceService

invoice_router = APIRouter(prefix="/purchase-orders/{po_id}/invoice", tags=["invoice"])


@invoice_router.post("", response_model=InvoiceOut)
async def create_invoice(
    po_id: uuid.UUID,
    body: InvoiceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    invoice = await InvoiceService.create(db, po_id, body, actor, get_client_ip(request))
    result = InvoiceOut.model_validate(invoice).model_dump(mode="json")
    await idempotency.store(result)
    return invoice


@invoice_router.patch("/{invoice_id}/acknowledge-discrepancy")
async def acknowledge_discrepancy(
    po_id: uuid.UUID,
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    await InvoiceService.acknowledge_discrepancy(db, invoice_id)
    return {"message": "Discrepancy acknowledged"}


@invoice_router.get("")
async def get_invoice(
    po_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await InvoiceService.get_for_actor(db, po_id, actor)
