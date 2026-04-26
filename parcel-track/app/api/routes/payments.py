"""Payment routes (admin-only; idempotent create)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import NotificationType, PaymentStatus, ShipmentStatus, UserRole
from app.db.database import get_db
from app.db.models import Invoice, Payment, User
from app.middleware.auth import financial_fields_allowed, get_client_ip, require_admin
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import PaymentCreate, PaymentOut
from app.services.notification_service import NotificationService
from app.services.shipment_service import ShipmentService

payment_router = APIRouter(prefix="/shipments/{shipment_id}/payments", tags=["payments"])


@payment_router.post("", response_model=PaymentOut)
async def add_payment(
    shipment_id: uuid.UUID,
    body: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    request: Request = None,
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    payment = Payment(shipment_id=shipment_id, status=PaymentStatus.CONFIRMED, **body.model_dump())
    db.add(payment)
    await db.flush()

    inv_result = await db.execute(select(Invoice).where(Invoice.shipment_id == shipment_id))
    invoice = inv_result.scalar_one_or_none()
    if invoice:
        total = await db.execute(
            select(func.sum(Payment.amount)).where(
                Payment.shipment_id == shipment_id,
                Payment.status == PaymentStatus.CONFIRMED,
            )
        )
        paid = total.scalar() or 0
        if paid >= invoice.value:
            shipment = await ShipmentService.get(db, shipment_id, actor)
            if shipment.status == ShipmentStatus.INVOICE_RECEIVED:
                await ShipmentService.transition_status(
                    db, shipment, ShipmentStatus.PAYMENT_CONFIRMED, actor, get_client_ip(request)
                )
                await NotificationService.notify_shipment_roles(
                    db,
                    shipment_id,
                    NotificationType.PAYMENT_CONFIRMED,
                    [UserRole.MOROCCO_AGENT],
                )

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
    q = select(Payment).where(Payment.shipment_id == shipment_id)
    page = await paginate(db, q, pagination)
    show = financial_fields_allowed(actor)
    page["items"] = [
        ShipmentService.mask_financials(PaymentOut.model_validate(p).model_dump(), show)
        for p in page["items"]
    ]
    return page
