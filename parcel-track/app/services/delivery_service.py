"""Delivery service — points, scheduling, and status updates."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import BookingStatus, DeliveryStatus, DeliveryType, NotificationType, UserRole
from app.core.exceptions import handle_integrity_error
from app.db.models import DeliveryContainer, DeliveryPoint, DeliverySchedule, User
from app.schemas.pagination import PaginationParams, paginate
from app.schemas.schemas import (
    DeliveryPointCreate,
    DeliveryScheduleCreate,
    DeliveryStatusUpdate,
)
from app.services.booking_service import BookingService
from app.services.container_lifecycle_service import ContainerLifecycleService
from app.services.notification_service import NotificationService


class DeliveryService:
    @staticmethod
    async def create_point(
        db: AsyncSession,
        booking_id: uuid.UUID,
        body: DeliveryPointCreate,
    ) -> DeliveryPoint:
        async with handle_integrity_error(
            "One or more containers are already assigned to a delivery point"
        ):
            point = DeliveryPoint(
                booking_id=booking_id,
                customer_user_id=body.customer_user_id,
                broker_id=body.broker_id,
                end_company_id=body.end_company_id,
                delivery_type=DeliveryType(body.delivery_type) if body.delivery_type else None,
                warehouse_name=body.warehouse_name,
                rebundled_at_warehouse=body.rebundled_at_warehouse,
                recipient_name=body.recipient_name,
                address=body.address,
                contact_name=body.contact_name,
                contact_phone=body.contact_phone,
                special_instructions=body.special_instructions,
            )
            db.add(point)
            await db.flush()

            for container_id in body.container_ids:
                db.add(DeliveryContainer(delivery_point_id=point.id, container_id=container_id))

        await db.flush()
        result = await db.execute(
            select(DeliveryPoint)
            .where(DeliveryPoint.id == point.id)
            .options(
                selectinload(DeliveryPoint.schedule),
                selectinload(DeliveryPoint.broker),
                selectinload(DeliveryPoint.end_company),
                selectinload(DeliveryPoint.container_assignments).selectinload(
                    DeliveryContainer.container
                ),
            )
        )
        return result.scalar_one()

    @staticmethod
    async def list_points(
        db: AsyncSession,
        booking_id: uuid.UUID,
        actor: User,
        pagination: PaginationParams,
    ) -> dict[str, Any]:
        q = select(DeliveryPoint).where(DeliveryPoint.booking_id == booking_id)

        if actor.role == UserRole.CUSTOMER:
            q = q.where(DeliveryPoint.customer_user_id == actor.id)

        q = q.options(
            selectinload(DeliveryPoint.container_assignments).selectinload(
                DeliveryContainer.container
            ),
            selectinload(DeliveryPoint.schedule),
            selectinload(DeliveryPoint.broker),
            selectinload(DeliveryPoint.end_company),
        )
        return await paginate(db, q, pagination)

    @staticmethod
    async def schedule(
        db: AsyncSession,
        booking_id: uuid.UUID,
        point_id: uuid.UUID,
        body: DeliveryScheduleCreate,
        actor: User,
    ) -> dict:
        if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
            raise HTTPException(403, "Only admin or UK agent can schedule delivery")

        result = await db.execute(select(DeliveryPoint).where(DeliveryPoint.id == point_id))
        point = result.scalar_one_or_none()
        if not point:
            raise HTTPException(404, "Delivery point not found")

        db.add(DeliverySchedule(delivery_point_id=point_id, **body.model_dump()))
        point.status = DeliveryStatus.SCHEDULED

        if point.customer_user_id:
            await NotificationService.send(
                db=db,
                user_id=point.customer_user_id,
                booking_id=booking_id,
                notification_type=NotificationType.DELIVERY_SCHEDULED,
                override_message=(
                    f"Your delivery is scheduled for {body.delivery_date}"
                    f" between {body.time_window_start}-{body.time_window_end}"
                ),
            )

        return {"message": "Delivery scheduled"}

    @staticmethod
    async def update_status(
        db: AsyncSession,
        booking_id: uuid.UUID,
        point_id: uuid.UUID,
        body: DeliveryStatusUpdate,
        actor: User,
        client_ip: str | None,
    ) -> dict:
        if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
            raise HTTPException(403, "Only admin or UK agent can update delivery status")

        result = await db.execute(
            select(DeliveryPoint)
            .where(DeliveryPoint.id == point_id)
            .options(selectinload(DeliveryPoint.schedule))
        )
        point = result.scalar_one_or_none()
        if not point:
            raise HTTPException(404, "Delivery point not found")

        new_status = DeliveryStatus(body.status)
        point.status = new_status

        if point.schedule:
            point.schedule.status = new_status
            if new_status == DeliveryStatus.DELIVERED:
                point.schedule.delivered_at = datetime.now(UTC)
            if new_status == DeliveryStatus.FAILED:
                point.schedule.failure_reason = body.failure_reason
                point.status = DeliveryStatus.AWAITING_SCHEDULE

        if new_status == DeliveryStatus.DELIVERED:
            # Fan the delivered-state out to every container at this point so
            # their lifecycle_status advances. The container-level state in
            # turn unlocks the booking's COMPLETE precondition once all
            # containers reach BANKED (or are explicitly acknowledged DISPUTED).
            assignments_q = await db.execute(
                select(DeliveryContainer.container_id).where(
                    DeliveryContainer.delivery_point_id == point_id
                )
            )
            await db.flush()
            for (container_id,) in assignments_q.all():
                await ContainerLifecycleService.recompute(db, container_id)

            # COMPLETE preconditions now check container lifecycle_status —
            # the precondition will reject if not all containers are BANKED,
            # so a single DELIVERED update from the route layer is allowed
            # to attempt the booking transition only if conditions are met.
            booking = await BookingService.get(db, booking_id, actor)
            try:
                await BookingService.transition_status(
                    db, booking, BookingStatus.COMPLETE, actor, client_ip
                )
            except HTTPException as exc:
                # The COMPLETE precondition legitimately rejects when
                # customers haven't paid yet (containers not BANKED). The
                # delivery write still succeeded; we just don't graduate
                # the booking. Anything other than a 400 propagates.
                if exc.status_code != 400:
                    raise

        return {"message": f"Delivery status updated to {new_status}"}
