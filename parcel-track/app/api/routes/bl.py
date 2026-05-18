"""Bill of Lading routes (Morocco agent writes, members read)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import BLStatus, BookingStatus, NotificationType, UserRole
from app.core.exceptions import handle_integrity_error
from app.db.database import get_db
from app.db.models import BillOfLading, Container, User, Vessel
from app.middleware.auth import get_client_ip, require_booking_member
from app.schemas.schemas import BLCreate, BLOut
from app.services.booking_service import BookingService
from app.services.notification_service import NotificationService

bl_router = APIRouter(prefix="/bookings/{booking_id}/bl", tags=["bill-of-lading"])


@bl_router.post("", response_model=BLOut)
async def upload_bl(
    booking_id: uuid.UUID,
    body: BLCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    if actor.role not in (UserRole.ADMIN, UserRole.MOROCCO_AGENT):
        raise HTTPException(403, "Only admin or Morocco agent can upload BL")

    async with handle_integrity_error("A BL or container number in this request already exists"):
        bl = BillOfLading(
            booking_id=booking_id,
            bl_number=body.bl_number,
            bl_date=body.bl_date,
            shipper_name=body.shipper_name,
            consignee_name=body.consignee_name,
            notify_party=body.notify_party,
            port_of_loading=body.port_of_loading,
            port_of_discharge=body.port_of_discharge,
            container_count=len(body.containers),
            commodity_description=body.commodity_description,
            gross_weight_kg=body.gross_weight_kg,
            status=BLStatus.UPLOADED,
        )
        db.add(bl)
        await db.flush()

        for c in body.containers:
            db.add(
                Container(
                    bl_id=bl.id, container_number=c.container_number, seal_number=c.seal_number
                )
            )

        bl.status = BLStatus.CONTAINERS_CREATED

    booking = await BookingService.get(db, booking_id, actor)
    await BookingService.transition_status(
        db, booking, BookingStatus.BL_ISSUED, actor, get_client_ip(request)
    )

    await NotificationService.notify_booking_roles(
        db, booking_id, NotificationType.BL_UPLOADED, [UserRole.ADMIN, UserRole.UK_AGENT]
    )

    await db.flush()
    result = await db.execute(
        select(BillOfLading)
        .where(BillOfLading.id == bl.id)
        .options(
            selectinload(BillOfLading.containers).selectinload(Container.broker),
            selectinload(BillOfLading.containers).selectinload(Container.end_company),
            selectinload(BillOfLading.vessel),
        )
    )
    return result.scalar_one()


@bl_router.get("", response_model=BLOut)
async def get_bl(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    result = await db.execute(
        select(BillOfLading)
        .where(BillOfLading.booking_id == booking_id)
        .options(
            selectinload(BillOfLading.containers).selectinload(Container.broker),
            selectinload(BillOfLading.containers).selectinload(Container.end_company),
            selectinload(BillOfLading.vessel).selectinload(Vessel.updates),
        )
    )
    bl = result.scalar_one_or_none()
    if not bl:
        raise HTTPException(404, "BL not found")
    return bl
