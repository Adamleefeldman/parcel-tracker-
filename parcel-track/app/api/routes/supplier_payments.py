"""Supplier payment routes (admin-only; idempotent create).

Supplier payments are USD outbound wires from us to the supplier (SCDB)
against a specific Invoice. One Invoice can take N payments (deposit +
balance, etc.). The cumulative-paid check that drives a booking's
PAYMENT_CONFIRMED transition lives in SupplierPaymentService.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, require_admin
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.schemas import SupplierPaymentCreate, SupplierPaymentOut
from app.services.supplier_payment_service import SupplierPaymentService

# Back-compat: the router name `payment_router` is what main.py / __init__.py
# import. The route path is now invoice-scoped (P0.3): payments hang off
# their Invoice, not the Booking aggregate.
payment_router = APIRouter(
    prefix="/invoices/{invoice_id}/supplier-payments", tags=["supplier-payments"]
)


@payment_router.post("", response_model=SupplierPaymentOut)
async def add_payment(
    invoice_id: uuid.UUID,
    body: SupplierPaymentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    payment = await SupplierPaymentService.add(db, invoice_id, body, actor, get_client_ip(request))
    result = SupplierPaymentOut.model_validate(payment).model_dump(mode="json")
    await idempotency.store(result)
    return payment


@payment_router.get("", response_model=PaginatedResponse[SupplierPaymentOut])
async def list_payments(
    invoice_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await SupplierPaymentService.list(db, invoice_id, actor, pagination)
