"""Payment service — add payments and trigger PAYMENT_CONFIRMED transition."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import NotificationType, PaymentStatus, ShipmentStatus, UserRole
from app.db.models import Invoice, Payment, User
from app.middleware.auth import financial_fields_allowed
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import PaymentCreate, PaymentOut
from app.services.notification_service import NotificationService
from app.services.shipment_service import ShipmentService


class PaymentService:
    @staticmethod
    async def add(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        body: PaymentCreate,
        actor: User,
        client_ip: str | None,
    ) -> Payment:
        payment = Payment(
            shipment_id=shipment_id, status=PaymentStatus.CONFIRMED, **body.model_dump()
        )
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
                        db, shipment, ShipmentStatus.PAYMENT_CONFIRMED, actor, client_ip
                    )
                    await NotificationService.notify_shipment_roles(
                        db,
                        shipment_id,
                        NotificationType.PAYMENT_CONFIRMED,
                        [UserRole.MOROCCO_AGENT],
                    )

        return payment

    @staticmethod
    async def list(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        actor: User,
        pagination: PaginationParams,
    ) -> PaginatedResponse:
        q = select(Payment).where(Payment.shipment_id == shipment_id)
        page = await paginate(db, q, pagination)
        show = financial_fields_allowed(actor)
        page["items"] = [
            ShipmentService.mask_financials(PaymentOut.model_validate(p).model_dump(), show)
            for p in page["items"]
        ]
        return page
