"""Container listing, port-status, and sale-side updates."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import require_admin, require_booking_member
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.schemas import ContainerOut, ContainerSaleUpdate, ContainerStatusUpdate
from app.services.container_service import ContainerService

container_router = APIRouter(prefix="/bookings/{booking_id}/containers", tags=["containers"])


@container_router.get("", response_model=PaginatedResponse[ContainerOut])
async def list_containers(
    booking_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    return await ContainerService.list(db, booking_id, pagination)


@container_router.patch("/{container_id}/port-status")
async def update_port_status(
    booking_id: uuid.UUID,
    container_id: uuid.UUID,
    body: ContainerStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    await ContainerService.update_port_status(db, container_id, body, actor)
    return {"message": "Container status updated"}


@container_router.patch("/{container_id}/sale", response_model=ContainerOut)
async def update_sale(
    booking_id: uuid.UUID,
    container_id: uuid.UUID,
    body: ContainerSaleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Set or amend the sale-side fields on a container (broker, end-company,
    delivery type, GBP sale prices). Admin-only — pricing is sensitive."""
    container = await ContainerService.update_sale(db, container_id, body, actor)
    # Reuse the helper from the bookings router for consistent serialisation.
    from app.api.routes.bookings import _container_to_out

    return _container_to_out(container)
