"""Purchase Order service — create, submit, and read POs."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentEntityType, NotificationType, POStatus, ShipmentStatus, UserRole
from app.core.exceptions import handle_integrity_error
from app.db.models import Document, PurchaseOrder, User
from app.middleware.auth import financial_fields_allowed
from app.schemas.schemas import POCreate, POOut
from app.services.notification_service import NotificationService
from app.services.shipment_service import ShipmentService


class PoService:
    @staticmethod
    async def create(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        body: POCreate,
    ) -> PurchaseOrder:
        existing = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.shipment_id == shipment_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(400, "PO already exists for this shipment")

        async with handle_integrity_error("A PO with this PO number already exists"):
            po = PurchaseOrder(shipment_id=shipment_id, **body.model_dump())
            db.add(po)
            await db.flush()

        await db.refresh(po)
        return po

    @staticmethod
    async def submit(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        po_id: uuid.UUID,
        actor: User,
        client_ip: str | None,
    ) -> None:
        result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
        po = result.scalar_one_or_none()
        if not po:
            raise HTTPException(404, "PO not found")

        doc = await db.execute(
            select(Document).where(
                Document.entity_type == DocumentEntityType.PURCHASE_ORDER,
                Document.entity_id == po_id,
            )
        )
        if not doc.scalar_one_or_none():
            raise HTTPException(400, "Document must be uploaded before submitting PO")

        po.status = POStatus.SUBMITTED

        shipment = await ShipmentService.get(db, shipment_id, actor)
        await ShipmentService.transition_status(
            db, shipment, ShipmentStatus.PO_SUBMITTED, actor, client_ip
        )

        await NotificationService.notify_shipment_roles(
            db,
            shipment_id,
            NotificationType.PO_SUBMITTED,
            [UserRole.ADMIN, UserRole.MOROCCO_AGENT],
        )

    @staticmethod
    async def get_for_actor(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        actor: User,
    ) -> dict:
        result = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.shipment_id == shipment_id)
        )
        po = result.scalar_one_or_none()
        if not po:
            raise HTTPException(404, "PO not found")

        data = POOut.model_validate(po).model_dump()
        return ShipmentService.mask_financials(data, financial_fields_allowed(actor))
