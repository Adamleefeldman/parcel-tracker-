"""Customer payment routes (admin-only; idempotent create).

Customer payments are GBP inbound from UK customers (brokers / end-buyers)
against a specific Container. Multi-tranche by design — the caller passes
tranche_index explicitly. The full aggregate-per-container view is exposed
via the GET endpoint.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import require_admin, require_booking_member
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.schemas import CustomerPaymentCreate, CustomerPaymentOut
from app.services.customer_payment_service import CustomerPaymentService

customer_payment_router = APIRouter(
    prefix="/bookings/{booking_id}/containers/{container_id}/customer-payments",
    tags=["customer-payments"],
)


@customer_payment_router.post("", response_model=CustomerPaymentOut)
async def add_customer_payment(
    booking_id: uuid.UUID,
    container_id: uuid.UUID,
    body: CustomerPaymentCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    payment = await CustomerPaymentService.add(db, container_id, body, actor)
    result = CustomerPaymentOut.model_validate(payment).model_dump(mode="json")
    await idempotency.store(result)
    return payment


@customer_payment_router.get("", response_model=PaginatedResponse[CustomerPaymentOut])
async def list_customer_payments(
    booking_id: uuid.UUID,
    container_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    return await CustomerPaymentService.list(db, container_id, actor, pagination)


@customer_payment_router.get("/aggregate")
async def aggregate_customer_payments(
    booking_id: uuid.UUID,
    container_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    """Return totals across all tranches: received, variance, expenses, banked.

    Money totals are masked to None for non-admin booking members; tranche_count
    stays visible.
    """
    agg = await CustomerPaymentService.aggregate_for_container(db, container_id, actor)
    # Strip the ORM tranche objects from the response — the list view above
    # returns those. Here we only want the rolled-up totals.
    return {k: v for k, v in agg.items() if k != "tranches"}
