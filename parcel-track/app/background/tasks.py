"""
Background jobs using Celery.
These run outside the request cycle — long-running tasks and scheduled checks.

Start the worker with:
    celery -A app.background.tasks worker --loglevel=info

Start the scheduler (for periodic tasks):
    celery -A app.background.tasks beat --loglevel=info
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

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
    beat_schedule={
        # Run every hour to check for vessels approaching without clearing docs
        "check-clearing-doc-deadlines": {
            "task": "app.background.tasks.check_clearing_doc_deadlines",
            "schedule": crontab(minute=0),  # top of every hour
        },
    },
)


# ── Tasks ──────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.background.tasks.check_clearing_doc_deadlines")
def check_clearing_doc_deadlines():
    """
    Scheduled: finds all in-transit shipments where:
    - Vessel ETA is within 48 hours
    - Clearing docs status is not COMPLETE
    Fires an urgent notification to admin + UK agent.
    """
    import asyncio
    from datetime import date, timedelta
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.db.database import AsyncSessionLocal
    from app.db.models import Shipment, BillOfLading, Vessel, ClearingDocs
    from app.core.enums import ShipmentStatus, ClearingDocsStatus, UserRole, NotificationType

    async def _run():
        async with AsyncSessionLocal() as db:
            cutoff = date.today() + timedelta(hours=48)
            result = await db.execute(
                select(Vessel)
                .join(BillOfLading, Vessel.bl_id == BillOfLading.id)
                .join(Shipment, BillOfLading.shipment_id == Shipment.id)
                .options(selectinload(Vessel.bill_of_lading))
                .where(
                    Shipment.status == ShipmentStatus.IN_TRANSIT,
                    Vessel.eta <= cutoff,
                    Vessel.eta >= date.today(),
                )
            )
            vessels = result.scalars().all()

            for vessel in vessels:
                bl = vessel.bill_of_lading
                docs_result = await db.execute(
                    select(ClearingDocs).where(ClearingDocs.shipment_id == bl.shipment_id)
                )
                docs = docs_result.scalar_one_or_none()

                if not docs or docs.status != ClearingDocsStatus.COMPLETE:
                    from app.services.notification_service import NotificationService
                    await NotificationService.notify_shipment_roles(
                        db=db,
                        shipment_id=bl.shipment_id,
                        notification_type=NotificationType.CLEARING_DOCS_URGENT,
                        roles=[UserRole.ADMIN, UserRole.UK_AGENT],
                        override_message=f"Vessel ETA is {vessel.eta} — clearing docs not yet complete.",
                    )

            await db.commit()

    asyncio.run(_run())


@celery_app.task(name="app.background.tasks.send_push_notification")
def send_push_notification(expo_token: str, title: str, body: str):
    """
    Async push dispatch — called from notification service when push can be deferred.
    Currently notification_service sends directly (synchronously); this task exists
    for high-volume scenarios where push should be queued.
    """
    import httpx
    payload = {"to": expo_token, "title": title, "body": body, "sound": "default"}
    try:
        httpx.post(settings.EXPO_PUSH_URL, json=payload, timeout=5.0)
    except Exception:
        pass  # non-fatal
