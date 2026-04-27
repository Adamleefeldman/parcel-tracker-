"""Container service — list containers and update port status."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PortStatus, UserRole
from app.db.models import BillOfLading, Container, User
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import ContainerStatusUpdate


class ContainerService:
    @staticmethod
    async def list(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        pagination: PaginationParams,
    ) -> PaginatedResponse:
        q = (
            select(Container)
            .join(BillOfLading, Container.bl_id == BillOfLading.id)
            .where(BillOfLading.shipment_id == shipment_id)
        )
        return await paginate(db, q, pagination)

    @staticmethod
    async def update_port_status(
        db: AsyncSession,
        container_id: uuid.UUID,
        body: ContainerStatusUpdate,
        actor: User,
    ) -> None:
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
