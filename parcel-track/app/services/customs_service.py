"""Customs service — upsert customs records and add notes.

This is the highest-leverage service: the all-containers-cleared → shipment CLEARED
cascade will also be called by the Destin8 poller (P1.4) without going through HTTP.
"""

import uuid

from fastapi import HTTPException
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
from app.db.models import BillOfLading, Container, CustomsNote, CustomsRecord, User
from app.schemas.schemas import CustomsNoteCreate, CustomsUpdate
from app.services.notification_service import NotificationService
from app.services.shipment_service import ShipmentService


class CustomsService:
    @staticmethod
    async def upsert(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        container_id: uuid.UUID,
        body: CustomsUpdate,
        actor: User,
        client_ip: str | None,
    ) -> CustomsRecord:
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
        if container is None:
            # Customs records reference container_id but the container row
            # itself can be missing if it was deleted, or hidden by RLS for
            # this actor's view. Either way, the cascade below assumes the
            # container exists — without this guard we crash on container.status.
            raise HTTPException(404, "Container not found")

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
                    db, shipment, ShipmentStatus.CLEARED, actor, client_ip
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

    @staticmethod
    async def add_note(
        db: AsyncSession,
        container_id: uuid.UUID,
        actor: User,
        body: CustomsNoteCreate,
    ) -> None:
        if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
            raise HTTPException(403, "Insufficient role")

        record_result = await db.execute(
            select(CustomsRecord).where(CustomsRecord.container_id == container_id)
        )
        record = record_result.scalar_one_or_none()
        if not record:
            raise HTTPException(404, "No customs record for this container")

        db.add(CustomsNote(customs_record_id=record.id, created_by=actor.id, note=body.note))
