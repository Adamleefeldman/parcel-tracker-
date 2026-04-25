"""Shipment CRUD and membership routes."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ShipmentStatus, UserRole
from app.db.database import get_db
from app.db.models import Shipment, ShipmentUser, User
from app.middleware.auth import get_current_user, require_admin, require_shipment_member
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import (
    ShipmentAddMember,
    ShipmentCreate,
    ShipmentDetailOut,
    ShipmentOut,
    ShipmentUpdate,
)
from app.services.shipment_service import ShipmentService

shipment_router = APIRouter(prefix="/shipments", tags=["shipments"])


@shipment_router.post("", response_model=ShipmentOut)
async def create_shipment(
    body: ShipmentCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    shipment = await ShipmentService.create(db, body.reference, actor)
    return shipment


@shipment_router.get("", response_model=PaginatedResponse[ShipmentOut])
async def list_shipments(
    status: ShipmentStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    if actor.role == UserRole.ADMIN:
        q = select(Shipment)
    else:
        q = (
            select(Shipment)
            .join(ShipmentUser, ShipmentUser.shipment_id == Shipment.id)
            .where(ShipmentUser.user_id == actor.id)
        )

    if status is not None:
        q = q.where(Shipment.status == status)
    if date_from is not None:
        q = q.where(Shipment.created_at >= date_from)
    if date_to is not None:
        q = q.where(Shipment.created_at <= date_to)

    return await paginate(db, q, pagination)


@shipment_router.get("/{shipment_id}", response_model=ShipmentDetailOut)
async def get_shipment(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    return await ShipmentService.get(db, shipment_id, actor)


@shipment_router.patch("/{shipment_id}", response_model=ShipmentOut)
async def update_shipment(
    shipment_id: uuid.UUID,
    body: ShipmentUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await ShipmentService.update(db, shipment_id, body.model_dump(exclude_unset=True), actor)


@shipment_router.post("/{shipment_id}/members")
async def add_member(
    shipment_id: uuid.UUID,
    body: ShipmentAddMember,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    shipment_result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    if not shipment_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    user_result = await db.execute(select(User).where(User.id == body.user_id, User.is_active))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = await db.execute(
        select(ShipmentUser).where(
            ShipmentUser.shipment_id == shipment_id,
            ShipmentUser.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this shipment",
        )

    membership = ShipmentUser(
        shipment_id=shipment_id,
        user_id=body.user_id,
        role_override=UserRole(body.role_override) if body.role_override else None,
    )
    db.add(membership)
    return {"message": "Member added"}
