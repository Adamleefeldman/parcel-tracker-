"""ContainerLifecycleService — single entry point that recomputes a
container's end-to-end lifecycle_status from its concrete events.

Inputs (read from the DB):
  - vessel.atd / vessel.ata        (transit milestones)
  - customs_record.status          (CLEARED?)
  - delivery point status          (DELIVERED?)
  - container.sale_price_total     (the target)
  - CustomerPayment rows           (banked_total, customer_invoice_ref)
  - container.dispute_reason / disputed_at (DISPUTED side state)

Output:
  Updates `container.lifecycle_status` in place. The caller is expected
  to be inside an active session that will commit (or roll back) the
  transaction. The recompute is idempotent: calling it twice yields the
  same value.

Why a derivation function (not a state machine):
  The customer-side leg has too many parallel events (variance, tranches,
  outbound invoices batching multiple containers) to model as a strict
  DAG. Re-computing from inputs after every event keeps the lifecycle
  state honest without a tangle of transition rules. The booking-level
  state machine (BookingService) still uses strict transitions —
  ContainerLifecycleStatus feeds *into* that machine via the COMPLETE
  precondition.

When to call:
  After any write that could change one of the inputs:
    - vessel depart (ATD set)
    - vessel update (ATA set)
    - customs status update
    - delivery point status update
    - customer payment add
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    ContainerLifecycleStatus,
    CustomsStatus,
    DeliveryStatus,
)
from app.db.models import (
    BillOfLading,
    Container,
    CustomerPayment,
    DeliveryContainer,
    DeliveryPoint,
    Vessel,
)


class ContainerLifecycleService:
    @staticmethod
    async def recompute(db: AsyncSession, container_id: uuid.UUID) -> ContainerLifecycleStatus:
        """Recompute and persist the container's lifecycle_status.

        Returns the new status. Does not commit — the caller's session
        is responsible for the surrounding transaction.
        """
        result = await db.execute(
            select(Container)
            .where(Container.id == container_id)
            .options(
                selectinload(Container.bill_of_lading).selectinload(BillOfLading.vessel),
                selectinload(Container.customs_record),
                selectinload(Container.delivery_assignments).selectinload(
                    DeliveryContainer.delivery_point
                ),
            )
        )
        container = result.scalar_one_or_none()
        if container is None:
            # The container was deleted in the same transaction — nothing to do.
            return ContainerLifecycleStatus.ORDERED

        new_status = await ContainerLifecycleService._derive(db, container)
        container.lifecycle_status = new_status
        return new_status

    @staticmethod
    async def _derive(db: AsyncSession, container: Container) -> ContainerLifecycleStatus:
        # DISPUTED side state takes precedence over everything else until
        # it's explicitly cleared.
        if container.dispute_reason and container.disputed_at:
            return ContainerLifecycleStatus.DISPUTED

        # ── Customer-financial leg (highest precedence after DISPUTED) ──
        # Sum tranches for this container and check against sale_price_total.
        # `bool_or` is Postgres-specific; we approximate it with COUNT over a
        # CASE expression so the same query works on SQLite for the test suite.
        any_invoiced_expr = func.count(case((CustomerPayment.customer_invoice_ref.is_not(None), 1)))
        sums_q = await db.execute(
            select(
                func.coalesce(func.sum(CustomerPayment.banked_total), 0),
                func.coalesce(func.sum(CustomerPayment.amount_received), 0),
                any_invoiced_expr,
            ).where(CustomerPayment.container_id == container.id)
        )
        total_banked_raw, total_received_raw, any_invoiced_count = sums_q.one()
        total_banked = Decimal(total_banked_raw)
        total_received = Decimal(total_received_raw)
        target = container.sale_price_total or Decimal("0")

        if target > 0 and total_banked >= target:
            return ContainerLifecycleStatus.BANKED
        if total_received > 0:
            return ContainerLifecycleStatus.PAID
        if any_invoiced_count > 0:
            return ContainerLifecycleStatus.INVOICED

        # ── Delivery / customs / transit leg ────────────────────────────
        # Delivered = at least one delivery point that contains this
        # container is in DELIVERED.
        delivered_q = await db.execute(
            select(func.count(DeliveryPoint.id))
            .join(DeliveryContainer, DeliveryContainer.delivery_point_id == DeliveryPoint.id)
            .where(
                DeliveryContainer.container_id == container.id,
                DeliveryPoint.status == DeliveryStatus.DELIVERED,
            )
        )
        delivered_count = delivered_q.scalar() or 0
        if delivered_count > 0:
            return ContainerLifecycleStatus.DELIVERED

        # Customs cleared at destination.
        if (
            container.customs_record is not None
            and container.customs_record.status == CustomsStatus.CLEARED
        ):
            return ContainerLifecycleStatus.IMPORT_CLEARED

        # Sea events come from the BL's vessel.
        bl = container.bill_of_lading
        vessel: Vessel | None = bl.vessel if bl else None
        if vessel is not None:
            if vessel.ata is not None:
                return ContainerLifecycleStatus.ARRIVED
            if vessel.atd is not None:
                return ContainerLifecycleStatus.AT_SEA

        return ContainerLifecycleStatus.ORDERED

    @staticmethod
    async def recompute_for_bl(db: AsyncSession, bl_id: uuid.UUID) -> None:
        """Recompute every container under a given BL. Used after vessel
        events that fan out across all containers on the same BL."""
        result = await db.execute(select(Container.id).where(Container.bl_id == bl_id))
        for (cid,) in result.all():
            await ContainerLifecycleService.recompute(db, cid)
