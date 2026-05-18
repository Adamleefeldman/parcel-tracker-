"""Container service — list, update port status, and update sale-side fields."""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import Currency, DeliveryType, PortStatus, UserRole
from app.db.models import BillOfLading, Broker, Company, Container, User
from app.schemas.pagination import PaginationParams, paginate
from app.schemas.schemas import ContainerSaleUpdate, ContainerStatusUpdate


class ContainerService:
    @staticmethod
    async def list(
        db: AsyncSession,
        booking_id: uuid.UUID,
        pagination: PaginationParams,
    ) -> dict[str, Any]:
        q = (
            select(Container)
            .join(BillOfLading, Container.bl_id == BillOfLading.id)
            .where(BillOfLading.booking_id == booking_id)
            .options(
                selectinload(Container.broker),
                selectinload(Container.end_company),
            )
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

    @staticmethod
    async def update_sale(
        db: AsyncSession,
        container_id: uuid.UUID,
        body: ContainerSaleUpdate,
        actor: User,
    ) -> Container:
        """
        Attach or amend the sale-side fields on a container: who's buying
        (broker + end_company), how it's delivered (direct vs warehouse),
        and at what GBP price. Admin-only — pricing is sensitive.

        Validates that the referenced broker and end company actually exist
        before binding the FKs. Missing → 404.
        """
        if actor.role != UserRole.ADMIN:
            raise HTTPException(403, "Only admin can set container sale fields")

        result = await db.execute(
            select(Container)
            .where(Container.id == container_id)
            .options(
                selectinload(Container.broker),
                selectinload(Container.end_company),
            )
        )
        container = result.scalar_one_or_none()
        if not container:
            raise HTTPException(404, "Container not found")

        if body.broker_id is not None:
            broker = await db.execute(select(Broker).where(Broker.id == body.broker_id))
            if not broker.scalar_one_or_none():
                raise HTTPException(404, "Broker not found")
            container.broker_id = body.broker_id

        if body.end_company_id is not None:
            company = await db.execute(select(Company).where(Company.id == body.end_company_id))
            if not company.scalar_one_or_none():
                raise HTTPException(404, "End company not found")
            container.end_company_id = body.end_company_id

        if body.delivery_type is not None:
            container.delivery_type = DeliveryType(body.delivery_type)
        if body.sale_price_per_tray is not None:
            container.sale_price_per_tray = body.sale_price_per_tray
        if body.sale_price_per_pallet is not None:
            container.sale_price_per_pallet = body.sale_price_per_pallet
        if body.sale_price_total is not None:
            container.sale_price_total = body.sale_price_total
        if body.sale_currency is not None:
            container.sale_currency = Currency(body.sale_currency)

        await db.flush()
        # Re-fetch with relationships so the response includes the broker/end_company objects.
        refreshed = await db.execute(
            select(Container)
            .where(Container.id == container_id)
            .options(
                selectinload(Container.broker),
                selectinload(Container.end_company),
            )
        )
        return refreshed.scalar_one()
