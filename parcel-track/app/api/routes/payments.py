"""Payment routes (admin-only; idempotent create)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, require_admin
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.schemas import PaymentCreate, PaymentOut
from app.services.payment_service import PaymentService

payment_router = APIRouter(prefix="/shipments/{shipment_id}/payments", tags=["payments"])


@payment_router.post("", response_model=PaymentOut)
async def add_payment(
    shipment_id: uuid.UUID,
    body: PaymentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    payment = await PaymentService.add(db, shipment_id, body, actor, get_client_ip(request))
    result = PaymentOut.model_validate(payment).model_dump(mode="json")
    await idempotency.store(result)
    return payment


@payment_router.get("", response_model=PaginatedResponse[PaymentOut])
async def list_payments(
    shipment_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await PaymentService.list(db, shipment_id, actor, pagination)
