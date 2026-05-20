"""Shipment-leg routes (P1.1 — multi-leg routes).

Legs hang off a booking and record the ordered transshipment route. Writes
are restricted to admin / Morocco agent (export-side logistics), matching the
vessel routes; reads are open to any booking member.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, require_booking_member
from app.schemas.schemas import ShipmentLegCreate, ShipmentLegOut, ShipmentLegUpdate
from app.services.shipment_leg_service import ShipmentLegService

shipment_leg_router = APIRouter(prefix="/bookings/{booking_id}/legs", tags=["shipment-legs"])

_WRITE_ROLES = (UserRole.ADMIN, UserRole.MOROCCO_AGENT)


@shipment_leg_router.post("", response_model=ShipmentLegOut)
async def create_leg(
    booking_id: uuid.UUID,
    body: ShipmentLegCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    if actor.role not in _WRITE_ROLES:
        raise HTTPException(403, "Only admin or Morocco agent can add shipment legs")
    return await ShipmentLegService.add(db, booking_id, body, actor, get_client_ip(request))


@shipment_leg_router.get("", response_model=list[ShipmentLegOut])
async def list_legs(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    return await ShipmentLegService.list_for_booking(db, booking_id)


@shipment_leg_router.patch("/{leg_id}", response_model=ShipmentLegOut)
async def update_leg(
    booking_id: uuid.UUID,
    leg_id: uuid.UUID,
    body: ShipmentLegUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    if actor.role not in _WRITE_ROLES:
        raise HTTPException(403, "Only admin or Morocco agent can edit shipment legs")
    return await ShipmentLegService.update(
        db, booking_id, leg_id, body, actor, get_client_ip(request)
    )
