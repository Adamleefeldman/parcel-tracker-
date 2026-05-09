"""Vessel routes (Morocco agent writes)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    ContainerStatus,
    NotificationType,
    PortStatus,
    ShipmentStatus,
    UserRole,
    VesselStatus,
    VesselUpdateStatus,
)
from app.db.database import get_db
from app.db.models import BillOfLading, Container, User, Vessel, VesselUpdate
from app.middleware.auth import get_client_ip, require_admin, require_shipment_member
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.schemas import VesselCreate, VesselDeparture, VesselOut, VesselUpdateCreate
from app.services.notification_service import NotificationService
from app.services.shipment_service import ShipmentService

vessel_router = APIRouter(prefix="/shipments/{shipment_id}/vessel", tags=["vessel"])


@vessel_router.post("", response_model=VesselOut)
async def create_vessel(
    shipment_id: uuid.UUID,
    body: VesselCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    if actor.role not in (UserRole.ADMIN, UserRole.MOROCCO_AGENT):
        raise HTTPException(403, "Only admin or Morocco agent can assign vessel")

    bl_result = await db.execute(
        select(BillOfLading).where(BillOfLading.shipment_id == shipment_id)
    )
    bl = bl_result.scalar_one_or_none()
    if not bl:
        raise HTTPException(400, "BL must be uploaded before assigning vessel")

    vessel = Vessel(bl_id=bl.id, **body.model_dump())
    db.add(vessel)
    await db.flush()
    result = await db.execute(
        select(Vessel).where(Vessel.id == vessel.id).options(selectinload(Vessel.updates))
    )
    return result.scalar_one()


@vessel_router.patch("/depart")
async def confirm_departure(
    shipment_id: uuid.UUID,
    body: VesselDeparture,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    if actor.role not in (UserRole.ADMIN, UserRole.MOROCCO_AGENT):
        raise HTTPException(403, "Only admin or Morocco agent can confirm departure")

    bl_result = await db.execute(
        select(BillOfLading)
        .where(BillOfLading.shipment_id == shipment_id)
        .options(selectinload(BillOfLading.vessel))
    )
    bl = bl_result.scalar_one_or_none()
    if bl is None:
        raise HTTPException(400, "BL must be uploaded before confirming departure")
    vessel = bl.vessel
    if vessel is None:
        raise HTTPException(400, "Vessel not assigned yet")

    vessel.atd = body.atd
    vessel.eta = body.eta
    vessel.status = VesselStatus.DEPARTED

    containers = await db.execute(select(Container).where(Container.bl_id == bl.id))
    for c in containers.scalars():
        c.status = ContainerStatus.IN_TRANSIT

    shipment = await ShipmentService.get(db, shipment_id, actor)
    await ShipmentService.transition_status(
        db, shipment, ShipmentStatus.IN_TRANSIT, actor, get_client_ip(request)
    )

    await NotificationService.notify_shipment_roles(
        db,
        shipment_id,
        NotificationType.VESSEL_DEPARTED,
        [UserRole.ADMIN, UserRole.UK_AGENT, UserRole.CUSTOMER],
    )
    return {"message": "Departure confirmed", "eta": body.eta}


@vessel_router.post("/updates", response_model=VesselOut)
async def add_vessel_update(
    shipment_id: uuid.UUID,
    body: VesselUpdateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    bl_result = await db.execute(
        select(BillOfLading)
        .where(BillOfLading.shipment_id == shipment_id)
        .options(selectinload(BillOfLading.vessel).selectinload(Vessel.updates))
    )
    bl = bl_result.scalar_one_or_none()
    if bl is None:
        raise HTTPException(400, "BL must be uploaded before recording vessel updates")
    vessel = bl.vessel
    if vessel is None:
        raise HTTPException(400, "No vessel found for this shipment")

    update = VesselUpdate(
        vessel_id=vessel.id,
        created_by=actor.id,
        status=VesselUpdateStatus(body.status),
        current_position_note=body.current_position_note,
        revised_eta=body.revised_eta,
    )
    db.add(update)

    if body.revised_eta:
        vessel.eta = body.revised_eta
        await NotificationService.notify_shipment_roles(
            db,
            shipment_id,
            NotificationType.VESSEL_DELAYED,
            [UserRole.ADMIN, UserRole.UK_AGENT, UserRole.CUSTOMER],
            override_message=f"Vessel ETA revised to {body.revised_eta}",
        )

    if body.status == VesselUpdateStatus.ARRIVED.value:
        await NotificationService.notify_shipment_roles(
            db,
            shipment_id,
            NotificationType.VESSEL_ARRIVED,
            [UserRole.ADMIN, UserRole.UK_AGENT],
        )
        containers = await db.execute(select(Container).where(Container.bl_id == bl.id))
        for c in containers.scalars():
            c.port_status = PortStatus.AWAITING_CUSTOMS
            c.status = ContainerStatus.AWAITING_CUSTOMS

    await idempotency.store(VesselOut.model_validate(vessel).model_dump(mode="json"))
    return vessel
