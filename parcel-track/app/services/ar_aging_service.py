"""A/R aging service (P1.4).

Flags containers that have been delivered (or invoiced / paid) but whose
customer payment has not yet been banked, and that have sat in that state
longer than `AR_AGING_THRESHOLD_DAYS`. Each aged container triggers one
notification to ADMIN + UK_AGENT, deduplicated to once per container per week
via a Redis key.

The aging signal is `Container.updated_at` (per ROADMAP) — a precise
`delivered_at` timestamp is deferred to P2.1.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ContainerLifecycleStatus, NotificationType, UserRole
from app.core.redis import get_redis_client
from app.db.models import BillOfLading, Container
from app.schemas.money_risk import AgedContainerOut, ARAgingBucket, ARAgingSummary
from app.services.notification_service import NotificationService

logger = logging.getLogger("parceltrack.celery")

# Containers in these lifecycle states have been delivered but not yet banked.
_UNBANKED_STATES = (
    ContainerLifecycleStatus.DELIVERED,
    ContainerLifecycleStatus.INVOICED,
    ContainerLifecycleStatus.PAID,
)
_DEDUP_TTL_SECONDS = 7 * 24 * 60 * 60  # once per container per week

# Inline container list cap on the money-risk summary (no silent truncation —
# `containers_truncated` flags when more rows exist than are returned).
_SUMMARY_CONTAINER_CAP = 50

# Aging bucket upper bounds (inclusive), in days. Anything above the last bound
# falls into the "60+" band. Keep in sync with the labels below.
_BUCKET_BOUNDS = ((14, "0-14"), (30, "15-30"), (60, "31-60"))
_OVERFLOW_LABEL = "60+"


class ARagingService:
    @staticmethod
    async def run(db: AsyncSession) -> int:
        """Scan for aged unbanked containers and notify. Returns the number of
        containers alerted on this run (after dedup)."""
        settings = get_settings()
        cutoff = datetime.now(UTC) - timedelta(days=settings.AR_AGING_THRESHOLD_DAYS)

        result = await db.execute(
            select(Container, BillOfLading.booking_id)
            .join(BillOfLading, Container.bl_id == BillOfLading.id)
            .where(
                Container.lifecycle_status.in_(_UNBANKED_STATES),
                Container.updated_at < cutoff,
            )
        )
        rows = result.all()

        redis = get_redis_client()
        alerted = 0
        for container, booking_id in rows:
            # Dedup: skip if this container was already alerted within the week.
            first_alert = await redis.set(
                f"ar_aging:notified:{container.id}", "1", nx=True, ex=_DEDUP_TTL_SECONDS
            )
            if not first_alert:
                continue
            await NotificationService.notify_booking_roles(
                db=db,
                booking_id=booking_id,
                notification_type=NotificationType.AR_AGING_ALERT,
                roles=[UserRole.ADMIN, UserRole.UK_AGENT],
                override_message=(
                    f"Container {container.container_number} has been "
                    f"{container.lifecycle_status.value} for over "
                    f"{settings.AR_AGING_THRESHOLD_DAYS} days without being banked."
                ),
            )
            alerted += 1

        logger.info("A/R aging check: %d aged container(s), %d alerted", len(rows), alerted)
        return alerted

    @staticmethod
    async def summary(db: AsyncSession) -> ARAgingSummary:
        """Read-only A/R exposure for the money-risk dashboard.

        Sums the **full** ``sale_price_total`` of every delivered-but-unbanked
        container (no netting against banked tranches) and buckets it by age.
        Age is ``now - Container.updated_at`` in whole days — the same proxy the
        alerter uses, so it is approximate (a precise ``delivered_at`` is
        deferred per ROADMAP). The inline container list is capped at
        ``_SUMMARY_CONTAINER_CAP``, ordered oldest-first; ``containers_truncated``
        flags when more rows exist than are returned.
        """
        now = datetime.now(UTC)

        result = await db.execute(
            select(Container, BillOfLading.booking_id)
            .join(BillOfLading, Container.bl_id == BillOfLading.id)
            .where(Container.lifecycle_status.in_(_UNBANKED_STATES))
            .order_by(Container.updated_at.asc())  # oldest (most aged) first
        )
        rows = result.all()

        bucket_counts = {label: 0 for _, label in _BUCKET_BOUNDS}
        bucket_counts[_OVERFLOW_LABEL] = 0
        bucket_amounts = {label: Decimal("0") for label in bucket_counts}

        total = Decimal("0")
        aged_containers: list[AgedContainerOut] = []
        for container, booking_id in rows:
            updated = container.updated_at
            # Older rows / SQLite may carry naive datetimes; treat as UTC.
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            days_aged = (now - updated).days
            amount = container.sale_price_total or Decimal("0")
            total += amount

            label = _OVERFLOW_LABEL
            for bound, candidate in _BUCKET_BOUNDS:
                if days_aged <= bound:
                    label = candidate
                    break
            bucket_counts[label] += 1
            bucket_amounts[label] += amount

            aged_containers.append(
                AgedContainerOut(
                    container_id=container.id,
                    container_number=container.container_number,
                    booking_id=booking_id,
                    lifecycle_status=container.lifecycle_status,
                    sale_price_total=container.sale_price_total,
                    days_aged=days_aged,
                )
            )

        buckets = [
            ARAgingBucket(label=label, count=bucket_counts[label], amount=bucket_amounts[label])
            for _, label in _BUCKET_BOUNDS
        ]
        buckets.append(
            ARAgingBucket(
                label=_OVERFLOW_LABEL,
                count=bucket_counts[_OVERFLOW_LABEL],
                amount=bucket_amounts[_OVERFLOW_LABEL],
            )
        )

        return ARAgingSummary(
            total_outstanding=total,
            container_count=len(rows),
            buckets=buckets,
            containers=aged_containers[:_SUMMARY_CONTAINER_CAP],
            containers_truncated=len(aged_containers) > _SUMMARY_CONTAINER_CAP,
        )
