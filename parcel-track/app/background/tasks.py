"""
Background jobs using Celery.
These run outside the request cycle — long-running tasks and scheduled checks.

Start the worker with:
    celery -A app.background.tasks worker --loglevel=info

Start the scheduler (for periodic tasks):
    celery -A app.background.tasks beat --loglevel=info
"""

import logging

import sentry_sdk
from celery import Celery
from celery.schedules import crontab
from celery.signals import after_setup_logger, after_setup_task_logger
from sentry_sdk.integrations.celery import CeleryIntegration

from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger("parceltrack.celery")

settings = get_settings()

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT or settings.APP_ENV,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[CeleryIntegration()],
    )

celery_app = Celery(
    "parceltrack",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.background.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_hijack_root_logger=False,
    beat_schedule={
        # Run every hour to check for vessels approaching without clearing docs
        "check-clearing-doc-deadlines": {
            "task": "app.background.tasks.check_clearing_doc_deadlines",
            "schedule": crontab(minute=0),  # top of every hour
        },
        # Poll VesselFinder for AIS positions on every fleet vessel.
        # `schedule` accepts a bare number (seconds) — this form supports
        # intervals > 60 minutes cleanly (which crontab does not).
        # The task itself no-ops when VESSELFINDER_ENABLED is false, so
        # registering the entry is safe even when the feature is dormant.
        "poll-vesselfinder": {
            "task": "app.background.tasks.poll_vesselfinder",
            "schedule": settings.VESSELFINDER_POLL_INTERVAL_MINUTES * 60,
        },
        # Daily A/R aging sweep — delivered-but-unbanked containers (P1.4).
        "check-ar-aging": {
            "task": "app.background.tasks.check_ar_aging",
            "schedule": crontab(hour=7, minute=0),
        },
        # Daily demurrage countdown — free-time about to expire (P1.5).
        "check-demurrage-countdown": {
            "task": "app.background.tasks.check_demurrage_countdown",
            "schedule": crontab(hour=7, minute=15),
        },
    },
)


# ── Logging setup for Celery workers ─────────────────────────────────────────


@after_setup_logger.connect
def _setup_celery_logger(**kwargs):
    setup_logging()


@after_setup_task_logger.connect
def _setup_celery_task_logger(**kwargs):
    setup_logging()


# ── Tasks ──────────────────────────────────────────────────────────────────────


@celery_app.task(name="app.background.tasks.check_clearing_doc_deadlines")
def check_clearing_doc_deadlines():
    """
    Scheduled: finds all in-transit bookings where:
    - Vessel ETA is within 2 days
    - Clearing docs status is not COMPLETE
    Fires an urgent notification to admin + UK agent.
    """
    import asyncio
    from datetime import date, timedelta

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.core.enums import BookingStatus, ClearingDocsStatus, NotificationType, UserRole
    from app.db.database import AsyncSessionLocal
    from app.db.models import BillOfLading, Booking, ClearingDocs, Vessel

    logger.info("Running clearing doc deadline check")

    async def _run():
        async with AsyncSessionLocal() as db:
            cutoff = date.today() + timedelta(days=2)
            result = await db.execute(
                select(Vessel)
                .join(BillOfLading, Vessel.bl_id == BillOfLading.id)
                .join(Booking, BillOfLading.booking_id == Booking.id)
                .options(selectinload(Vessel.bill_of_lading))
                .where(
                    Booking.status == BookingStatus.IN_TRANSIT,
                    Vessel.eta <= cutoff,
                    Vessel.eta >= date.today(),
                )
            )
            vessels = result.scalars().all()

            for vessel in vessels:
                bl = vessel.bill_of_lading
                docs_result = await db.execute(
                    select(ClearingDocs).where(ClearingDocs.booking_id == bl.booking_id)
                )
                docs = docs_result.scalar_one_or_none()

                if not docs or docs.status != ClearingDocsStatus.COMPLETE:
                    from app.services.notification_service import NotificationService

                    await NotificationService.notify_booking_roles(
                        db=db,
                        booking_id=bl.booking_id,
                        notification_type=NotificationType.CLEARING_DOCS_URGENT,
                        roles=[UserRole.ADMIN, UserRole.UK_AGENT],
                        override_message=(
                            f"Vessel ETA is {vessel.eta} — clearing docs not yet complete."
                        ),
                    )

            await db.commit()
            logger.info("Clearing doc deadline check complete, matched %d vessels", len(vessels))

    asyncio.run(_run())


@celery_app.task(
    name="app.background.tasks.send_push_notification",
    bind=True,
    autoretry_for=(),  # custom retry below — we only retry transient provider errors
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def send_push_notification(self, notification_id: str):
    """
    Dispatch an Expo push for a single Notification row.

    Contract:
      - Takes the notification id (string UUID). The task re-reads the row so
        that a token refresh between enqueue and dispatch is honoured.
      - Uses the shared integrations HTTP helper (timeouts, retries, breaker).
      - Marks `notification.push_sent = True` on success.
      - Retries with backoff on `IntegrationTimeout` / `IntegrationUnavailable`
        (Expo 5xx or network issues).
      - Gives up silently on 4xx — usually `DeviceNotRegistered` for a stale
        token. Retrying won't help; the token needs to be refreshed client-side.
    """
    import asyncio
    import uuid as _uuid

    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal
    from app.db.models import Notification, User
    from app.integrations._exceptions import (
        IntegrationError,
        IntegrationTimeout,
        IntegrationUnavailable,
    )
    from app.integrations._http import build_client, request

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            notif = await db.get(Notification, _uuid.UUID(notification_id))
            if notif is None:
                # Caller committed something else but the notification row is gone
                # — nothing to do. (Shouldn't happen in practice; safeguard only.)
                logger.warning("send_push_notification: row %s not found", notification_id)
                return
            if notif.push_sent:
                return  # idempotent — retries are safe
            user = (
                await db.execute(select(User).where(User.id == notif.user_id))
            ).scalar_one_or_none()
            if user is None or not user.expo_push_token:
                return

            payload = {
                "to": user.expo_push_token,
                "title": notif.title,
                "body": notif.message,
                "sound": "default",
            }

            async with build_client("expo") as client:
                await request(
                    "expo",
                    client,
                    "POST",
                    settings.EXPO_PUSH_URL,
                    json=payload,
                )

            notif.push_sent = True
            await db.commit()

    try:
        asyncio.run(_run())
    except (IntegrationTimeout, IntegrationUnavailable) as exc:
        # Transient — let Celery retry with exponential backoff.
        raise self.retry(exc=exc, countdown=2**self.request.retries) from exc
    except IntegrationError:
        # 4xx / auth / rate-limit — retrying won't help; log and drop.
        logger.warning("push_notification permanent failure id=%s", notification_id, exc_info=True)


@celery_app.task(
    name="app.background.tasks.poll_vesselfinder",
    bind=True,
    max_retries=3,
)
def poll_vesselfinder(self):
    """Periodic VesselFinder fleet poll (P1.5).

    Beat fires this every `VESSELFINDER_POLL_INTERVAL_MINUTES`. The task is
    a thin shell — all logic lives in `VesselPollService.poll_vessels_once`.

    Disabled by default: returns immediately when `VESSELFINDER_ENABLED` is
    false so the entry can stay in the beat schedule even before the API
    key + fleet are wired up in production.

    Retry policy: transient integration errors (timeouts, 5xx, circuit open)
    bounce with exponential backoff. Auth errors (`IntegrationAuthError`)
    are NOT retried — they mean the key is wrong or the fleet config is
    missing, and a thousand retries won't fix that. Per-vessel errors
    inside the service layer are caught there and don't bubble up.
    """
    import asyncio

    from app.db.database import AsyncSessionLocal
    from app.integrations._exceptions import (
        IntegrationError,
        IntegrationRateLimited,
        IntegrationTimeout,
        IntegrationUnavailable,
    )
    from app.services.vessel_poll_service import VesselPollService

    if not settings.VESSELFINDER_ENABLED:
        logger.debug("poll_vesselfinder skipped — VESSELFINDER_ENABLED is false")
        return {"skipped": "disabled"}

    async def _run() -> dict[str, int]:
        async with AsyncSessionLocal() as db:
            summary = await VesselPollService().poll_vessels_once(db)
            return summary.as_dict()

    try:
        return asyncio.run(_run())
    except (IntegrationTimeout, IntegrationUnavailable, IntegrationRateLimited) as exc:
        raise self.retry(exc=exc, countdown=2**self.request.retries) from exc
    except IntegrationError:
        # Auth error or other terminal integration fault — log and drop.
        # Retrying won't fix a bad key.
        logger.warning("poll_vesselfinder permanent failure", exc_info=True)
        return {"error": "permanent"}


@celery_app.task(name="app.background.tasks.check_ar_aging")
def check_ar_aging():
    """Daily (P1.4): flag delivered/invoiced/paid containers that have not been
    banked past the A/R aging threshold. No-ops when AR_AGING_ENABLED is false.
    All logic lives in ARagingService — this is a thin Celery shell."""
    import asyncio

    from app.db.database import AsyncSessionLocal
    from app.services.ar_aging_service import ARagingService

    if not settings.AR_AGING_ENABLED:
        logger.debug("check_ar_aging skipped — AR_AGING_ENABLED is false")
        return {"skipped": "disabled"}

    async def _run() -> dict[str, int]:
        async with AsyncSessionLocal() as db:
            alerted = await ARagingService.run(db)
            await db.commit()
            return {"alerted": alerted}

    return asyncio.run(_run())


@celery_app.task(name="app.background.tasks.check_demurrage_countdown")
def check_demurrage_countdown():
    """Daily (P1.5): warn when a container's free demurrage time at the UK port
    is about to expire. No-ops when DEMURRAGE_ALERTS_ENABLED is false. All logic
    lives in DemurrageService — this is a thin Celery shell."""
    import asyncio

    from app.db.database import AsyncSessionLocal
    from app.services.demurrage_service import DemurrageService

    if not settings.DEMURRAGE_ALERTS_ENABLED:
        logger.debug("check_demurrage_countdown skipped — DEMURRAGE_ALERTS_ENABLED is false")
        return {"skipped": "disabled"}

    async def _run() -> dict[str, int]:
        async with AsyncSessionLocal() as db:
            alerted = await DemurrageService.run(db)
            await db.commit()
            return {"alerted": alerted}

    return asyncio.run(_run())
