"""Customs clearance routes (UK agent writes per container)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    ContainerStatus,
    CustomsStatus,
    NotificationType,
    PortStatus,
    ShipmentStatus,
    UserRole,
)
from app.db.database import get_db
from app.db.models import BillOfLading, Container, CustomsNote, CustomsRecord, User
from app.middleware.auth import get_client_ip, require_shipment_member
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.schemas import CustomsNoteCreate, CustomsRecordOut, CustomsUpdate
from app.services.notification_service import NotificationService
from app.services.shipment_service import ShipmentService

customs_router = APIRouter(
    prefix="/shipments/{shipment_id}/containers/{container_id}/customs", tags=["customs"]
)


@customs_router.put("", response_model=CustomsRecordOut)
async def upsert_customs(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: CustomsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    request: Request = None,
):
    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Only admin or UK agent can update customs status")

    result = await db.execute(
        select(CustomsRecord)
        .where(CustomsRecord.container_id == container_id)
        .options(selectinload(CustomsRecord.notes))
    )
    record = result.scalar_one_or_none()

    if not record:
        record = CustomsRecord(container_id=container_id)
        db.add(record)
        await db.flush()

    new_status = CustomsStatus(body.status)
    record.status = new_status

    if body.clearance_date:
        record.clearance_date = body.clearance_date
    if body.hold_reason:
        record.hold_reason = body.hold_reason
    if body.hmrc_ref:
        record.hmrc_ref = body.hmrc_ref
    if body.duty_paid is not None:
        record.duty_paid = body.duty_paid

    container_result = await db.execute(select(Container).where(Container.id == container_id))
    container = container_result.scalar_one_or_none()

    if new_status == CustomsStatus.CLEARED:
        container.status = ContainerStatus.CLEARED
        container.port_status = PortStatus.RELEASED
        await NotificationService.notify_shipment_roles(
            db, shipment_id, NotificationType.CONTAINER_CLEARED, [UserRole.ADMIN]
        )
        all_containers = await db.execute(
            select(Container)
            .join(BillOfLading, Container.bl_id == BillOfLading.id)
            .where(BillOfLading.shipment_id == shipment_id)
        )
        containers = all_containers.scalars().all()
        if all(c.status == ContainerStatus.CLEARED for c in containers):
            shipment = await ShipmentService.get(db, shipment_id, actor)
            await ShipmentService.transition_status(
                db, shipment, ShipmentStatus.CLEARED, actor, get_client_ip(request)
            )

    elif new_status in (CustomsStatus.ON_HOLD, CustomsStatus.EXAMINATION):
        container.status = ContainerStatus.ON_HOLD
        container.port_status = PortStatus.CUSTOMS_HOLD
        await NotificationService.notify_shipment_roles(
            db,
            shipment_id,
            NotificationType.CONTAINER_HOLD,
            [UserRole.ADMIN],
            override_message=(
                f"Container {container.container_number} placed on hold: {body.hold_reason}"
            ),
        )

    await db.flush()
    refreshed = await db.execute(
        select(CustomsRecord)
        .where(CustomsRecord.id == record.id)
        .options(selectinload(CustomsRecord.notes))
    )
    return refreshed.scalar_one()


@customs_router.post("/notes")
async def add_customs_note(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: CustomsNoteCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Insufficient role")

    record_result = await db.execute(
        select(CustomsRecord).where(CustomsRecord.container_id == container_id)
    )
    record = record_result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "No customs record for this container")

    db.add(CustomsNote(customs_record_id=record.id, created_by=actor.id, note=body.note))
    result = {"message": "Note added"}
    await idempotency.store(result)
    return result
