"""Demurrage countdown service (P1.5).

Once a vessel has arrived (`Vessel.ata` set), the container's free demurrage
time at the UK port starts counting down. When the remaining free time falls
within `DEMURRAGE_WARNING_LEAD_DAYS` (or has already expired), this fires a
warning to ADMIN + UK_AGENT, deduplicated to once per booking per day.

Free-time per booking comes from `Booking.free_days_demurrage` (populated from
the carrier confirmation in P1.2, optionally via a PortTemplate in P1.3);
`DEMURRAGE_DEFAULT_FREE_DAYS` is the fallback when it is unset.
"""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import BookingStatus, NotificationType, UserRole
from app.core.redis import get_redis_client
from app.db.models import BillOfLading, Booking, Container, Vessel
from app.schemas.money_risk import DemurrageCountdownOut, DemurrageSummary
from app.services.notification_service import NotificationService

logger = logging.getLogger("parceltrack.celery")

_DEDUP_TTL_SECONDS = 24 * 60 * 60  # once per booking per day


def days_left(ata: date, free_days: int, today: date) -> int:
    """Free demurrage days remaining. Negative means free time has expired."""
    return free_days - (today - ata).days


class DemurrageService:
    @staticmethod
    async def run(db: AsyncSession) -> int:
        """Scan arrived vessels and warn on near/expired demurrage free time.
        Returns the number of bookings alerted on this run (after dedup)."""
        settings = get_settings()
        today = date.today()

        result = await db.execute(
            select(Vessel, Booking)
            .join(BillOfLading, Vessel.bl_id == BillOfLading.id)
            .join(Booking, BillOfLading.booking_id == Booking.id)
            .where(
                Vessel.ata.is_not(None),
                Booking.status != BookingStatus.COMPLETE,
            )
        )
        rows = result.all()

        redis = get_redis_client()
        alerted = 0
        for vessel, booking in rows:
            free_days = booking.free_days_demurrage or settings.DEMURRAGE_DEFAULT_FREE_DAYS
            remaining = days_left(vessel.ata, free_days, today)
            if remaining > settings.DEMURRAGE_WARNING_LEAD_DAYS:
                continue

            first_alert = await redis.set(
                f"demurrage:notified:{booking.id}:{today.isoformat()}",
                "1",
                nx=True,
                ex=_DEDUP_TTL_SECONDS,
            )
            if not first_alert:
                continue

            if remaining >= 0:
                msg = (
                    f"Demurrage free time expires in {remaining} day(s) "
                    f"(arrived {vessel.ata}, {free_days} free days)."
                )
            else:
                msg = (
                    f"Demurrage free time expired {abs(remaining)} day(s) ago "
                    f"(arrived {vessel.ata}, {free_days} free days)."
                )
            await NotificationService.notify_booking_roles(
                db=db,
                booking_id=booking.id,
                notification_type=NotificationType.DEMURRAGE_WARNING,
                roles=[UserRole.ADMIN, UserRole.UK_AGENT],
                override_message=msg,
            )
            alerted += 1

        logger.info("Demurrage check: %d arrived vessel(s), %d alerted", len(rows), alerted)
        return alerted

    @staticmethod
    async def countdown(db: AsyncSession) -> DemurrageSummary:
        """Read-only per-container demurrage countdown for the money-risk dashboard.

        One row per container under an arrived vessel (matching the prototype's
        per-container list). ``days_remaining`` is whole days via the shared
        :func:`days_left` — ``Vessel.ata`` is a date, so no hour precision is
        invented; a negative value means free time has already expired. Rows are
        sorted soonest-expiring first.
        """
        settings = get_settings()
        today = date.today()

        result = await db.execute(
            select(
                Container,
                Vessel.ata,
                BillOfLading.port_of_discharge,
                Booking.id,
                Booking.free_days_demurrage,
                Booking.demurrage_rate_gbp_after,
            )
            .join(BillOfLading, Container.bl_id == BillOfLading.id)
            .join(Vessel, Vessel.bl_id == BillOfLading.id)
            .join(Booking, BillOfLading.booking_id == Booking.id)
            .where(
                Vessel.ata.is_not(None),
                Booking.status != BookingStatus.COMPLETE,
            )
        )

        items: list[DemurrageCountdownOut] = []
        for container, ata, port, booking_id, free_days_demurrage, rate in result.all():
            free_days = free_days_demurrage or settings.DEMURRAGE_DEFAULT_FREE_DAYS
            remaining = days_left(ata, free_days, today)
            items.append(
                DemurrageCountdownOut(
                    booking_id=booking_id,
                    container_id=container.id,
                    container_number=container.container_number,
                    port_of_discharge=port,
                    ata=ata,
                    free_days=free_days,
                    days_remaining=remaining,
                    expired=remaining < 0,
                    rate_gbp_after=rate,
                )
            )

        items.sort(key=lambda i: i.days_remaining)
        expiring_count = sum(
            1 for i in items if i.days_remaining <= settings.DEMURRAGE_WARNING_LEAD_DAYS
        )
        soonest = items[0].days_remaining if items else None

        return DemurrageSummary(
            expiring_count=expiring_count,
            soonest_days_remaining=soonest,
            items=items,
        )
