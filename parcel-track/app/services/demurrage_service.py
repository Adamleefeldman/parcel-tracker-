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
from app.db.models import BillOfLading, Booking, Vessel
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
