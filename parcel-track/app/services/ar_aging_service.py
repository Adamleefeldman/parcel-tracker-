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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ContainerLifecycleStatus, NotificationType, UserRole
from app.core.redis import get_redis_client
from app.db.models import BillOfLading, Container
from app.services.notification_service import NotificationService

logger = logging.getLogger("parceltrack.celery")

# Containers in these lifecycle states have been delivered but not yet banked.
_UNBANKED_STATES = (
    ContainerLifecycleStatus.DELIVERED,
    ContainerLifecycleStatus.INVOICED,
    ContainerLifecycleStatus.PAID,
)
_DEDUP_TTL_SECONDS = 7 * 24 * 60 * 60  # once per container per week


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
