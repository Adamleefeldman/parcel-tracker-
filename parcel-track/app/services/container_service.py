"""Container service — list, update port status, update sale-side fields,
and open / acknowledge disputes."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    ContainerLifecycleStatus,
    Currency,
    DeliveryType,
    PortStatus,
    UserRole,
)
from app.db.models import AuditLog, BillOfLading, Broker, Company, Container, User
from app.schemas.pagination import PaginationParams, paginate
from app.schemas.schemas import ContainerSaleUpdate, ContainerStatusUpdate
from app.services.container_lifecycle_service import ContainerLifecycleService


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
    async def get_in_booking(
        db: AsyncSession,
        booking_id: uuid.UUID,
        container_id: uuid.UUID,
        *,
        options: tuple[Any, ...] = (),
    ) -> Container:
        """Load a container, asserting it belongs to ``booking_id``.

        A Container has no direct ``booking_id``; it is scoped to a booking only
        through ``Container.bl_id -> BillOfLading.booking_id``. Endpoints nested
        under ``/bookings/{booking_id}/containers/{container_id}`` MUST verify that
        link — otherwise the path's ``booking_id`` is decorative and a caller can
        address any container under any booking. Raises 404 when the container does
        not exist or lives under a different booking.
        """
        q = (
            select(Container)
            .join(BillOfLading, Container.bl_id == BillOfLading.id)
            .where(Container.id == container_id, BillOfLading.booking_id == booking_id)
            .options(*options)
        )
        result = await db.execute(q)
        container = result.scalar_one_or_none()
        if container is None:
            raise HTTPException(404, "Container not found")
        return container

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

    # ── Dispute open / acknowledge (P2.1) ──────────────────────────────────

    @staticmethod
    async def _get_container_for_dispute(db: AsyncSession, container_id: uuid.UUID) -> Container:
        result = await db.execute(
            select(Container)
            .where(Container.id == container_id)
            .options(
                selectinload(Container.bill_of_lading),
                selectinload(Container.broker),
                selectinload(Container.end_company),
            )
        )
        container = result.scalar_one_or_none()
        if not container:
            raise HTTPException(404, "Container not found")
        return container

    @staticmethod
    async def open_dispute(
        db: AsyncSession,
        container_id: uuid.UUID,
        reason: str,
        actor: User,
        client_ip: str | None,
    ) -> Container:
        """Mark a container as disputed. Re-opening a previously-acknowledged
        dispute clears the acknowledgement so the booking is blocked again."""
        if actor.role != UserRole.ADMIN:
            raise HTTPException(403, "Only admin can open a dispute")

        container = await ContainerService._get_container_for_dispute(db, container_id)
        old = {
            "dispute_reason": container.dispute_reason,
            "disputed_at": container.disputed_at.isoformat() if container.disputed_at else None,
            "dispute_acknowledged_at": (
                container.dispute_acknowledged_at.isoformat()
                if container.dispute_acknowledged_at
                else None
            ),
        }

        container.dispute_reason = reason
        container.disputed_at = datetime.now(UTC)
        # Re-opening clears any prior acknowledgement.
        container.dispute_acknowledged_at = None
        container.dispute_acknowledged_by = None
        await db.flush()

        # Recompute mutates lifecycle_status to DISPUTED in memory. Flush
        # again before refresh — otherwise the upcoming refresh() reads back
        # the stale lifecycle from the DB and overwrites our change.
        await ContainerLifecycleService.recompute(db, container_id)
        await db.flush()

        new = {
            "dispute_reason": container.dispute_reason,
            "disputed_at": container.disputed_at.isoformat(),
            "dispute_acknowledged_at": None,
        }
        booking_id = container.bill_of_lading.booking_id if container.bill_of_lading else None
        db.add(
            AuditLog(
                booking_id=booking_id,
                actor_id=actor.id,
                action="container.dispute_opened",
                entity_type="container",
                entity_id=container.id,
                old_value=json.dumps(old),
                new_value=json.dumps(new),
                ip_address=client_ip,
            )
        )
        await db.refresh(container)
        return container

    @staticmethod
    async def acknowledge_dispute(
        db: AsyncSession,
        container_id: uuid.UUID,
        actor: User,
        client_ip: str | None,
    ) -> Container:
        """Acknowledge an open dispute. Preserves `dispute_reason` /
        `disputed_at` (history) and keeps `lifecycle_status == DISPUTED` —
        the booking COMPLETE precondition treats acknowledged disputes as
        resolved."""
        if actor.role != UserRole.ADMIN:
            raise HTTPException(403, "Only admin can acknowledge a dispute")

        container = await ContainerService._get_container_for_dispute(db, container_id)
        if container.lifecycle_status != ContainerLifecycleStatus.DISPUTED:
            raise HTTPException(400, "Container is not currently disputed")

        container.dispute_acknowledged_at = datetime.now(UTC)
        container.dispute_acknowledged_by = actor.id
        await db.flush()

        db.add(
            AuditLog(
                booking_id=container.bill_of_lading.booking_id
                if container.bill_of_lading
                else None,
                actor_id=actor.id,
                action="container.dispute_acknowledged",
                entity_type="container",
                entity_id=container.id,
                old_value=None,
                new_value=json.dumps(
                    {
                        "dispute_acknowledged_at": container.dispute_acknowledged_at.isoformat(),
                        "dispute_acknowledged_by": str(actor.id),
                    }
                ),
                ip_address=client_ip,
            )
        )
        await db.refresh(container)
        return container
