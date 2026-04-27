"""Container listing and port-status updates."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import require_shipment_member
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.schemas import ContainerOut, ContainerStatusUpdate
from app.services.container_service import ContainerService

container_router = APIRouter(prefix="/shipments/{shipment_id}/containers", tags=["containers"])


@container_router.get("", response_model=PaginatedResponse[ContainerOut])
async def list_containers(
    shipment_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    return await ContainerService.list(db, shipment_id, pagination)


@container_router.patch("/{container_id}/port-status")
async def update_port_status(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: ContainerStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    await ContainerService.update_port_status(db, container_id, body, actor)
    return {"message": "Container status updated"}
