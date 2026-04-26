"""Container listing and port-status updates."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PortStatus, UserRole
from app.db.database import get_db
from app.db.models import BillOfLading, Container, User
from app.middleware.auth import require_shipment_member
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import ContainerOut, ContainerStatusUpdate

container_router = APIRouter(prefix="/shipments/{shipment_id}/containers", tags=["containers"])


@container_router.get("", response_model=PaginatedResponse[ContainerOut])
async def list_containers(
    shipment_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    q = (
        select(Container)
        .join(BillOfLading, Container.bl_id == BillOfLading.id)
        .where(BillOfLading.shipment_id == shipment_id)
    )
    return await paginate(db, q, pagination)


@container_router.patch("/{container_id}/port-status")
async def update_port_status(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: ContainerStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Only admin or UK agent can update container status")

    result = await db.execute(select(Container).where(Container.id == container_id))
    container = result.scalar_one_or_none()
    if not container:
        raise HTTPException(404, "Container not found")

    if body.port_status:
        container.port_status = PortStatus(body.port_status)
    if body.destin8_ref:
        container.destin8_ref = body.destin8_ref
    if body.notes:
        container.notes = body.notes

    return {"message": "Container status updated"}
