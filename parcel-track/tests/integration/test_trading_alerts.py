"""Integration tests for P1.4 (A/R aging) and P1.5 (demurrage countdown).

Each service is exercised directly against a seeded database — the Celery
task wrappers are thin and only add the enable-flag guard + asyncio bridge.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.enums import ContainerLifecycleStatus, NotificationType
from app.db.models import BillOfLading, Container, Notification, Vessel
from app.services.ar_aging_service import ARagingService
from app.services.demurrage_service import DemurrageService
from tests.integration.conftest import TestSession, advance_to


async def _count_notifications(booking_id: str, notif_type: NotificationType) -> int:
    async with TestSession() as db:
        result = await db.execute(
            select(Notification).where(
                Notification.booking_id == uuid.UUID(booking_id),
                Notification.type == notif_type,
            )
        )
        return len(list(result.scalars().all()))


async def _age_container(container_id: str, *, days: int) -> None:
    """Mark a container delivered-but-unbanked and `days` old."""
    async with TestSession() as db:
        await db.execute(
            update(Container)
            .where(Container.id == uuid.UUID(container_id))
            .values(
                lifecycle_status=ContainerLifecycleStatus.DELIVERED,
                updated_at=datetime.now(UTC) - timedelta(days=days),
            )
        )
        await db.commit()


async def _set_vessel_ata(booking_id: str, ata: date) -> None:
    async with TestSession() as db:
        vessel = (
            await db.execute(
                select(Vessel)
                .join(BillOfLading, Vessel.bl_id == BillOfLading.id)
                .where(BillOfLading.booking_id == uuid.UUID(booking_id))
            )
        ).scalar_one()
        vessel.ata = ata
        await db.commit()


class TestARaging:
    async def test_aged_unbanked_container_alerts(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "ARAGE-1")
        await _age_container(ctx["container_ids"][0], days=20)

        async with TestSession() as db:
            alerted = await ARagingService.run(db)
            await db.commit()

        assert alerted >= 1
        assert await _count_notifications(bid, NotificationType.AR_AGING_ALERT) >= 1

    async def test_recent_container_not_alerted(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "ARAGE-2")
        # Delivered but updated just now (default updated_at) — not aged.
        async with TestSession() as db:
            await db.execute(
                update(Container)
                .where(Container.id == uuid.UUID(ctx["container_ids"][0]))
                .values(lifecycle_status=ContainerLifecycleStatus.DELIVERED)
            )
            await db.commit()

        async with TestSession() as db:
            alerted = await ARagingService.run(db)
            await db.commit()

        assert alerted == 0
        assert await _count_notifications(bid, NotificationType.AR_AGING_ALERT) == 0

    async def test_dedup_blocks_second_run(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "ARAGE-3")
        await _age_container(ctx["container_ids"][0], days=20)

        async with TestSession() as db:
            await ARagingService.run(db)
            await db.commit()
        first = await _count_notifications(bid, NotificationType.AR_AGING_ALERT)

        async with TestSession() as db:
            alerted2 = await ARagingService.run(db)
            await db.commit()

        assert alerted2 == 0  # deduped within the week
        assert await _count_notifications(bid, NotificationType.AR_AGING_ALERT) == first


class TestDemurrage:
    async def test_overdue_demurrage_alerts(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, _ = await advance_to(client, h, "in_transit", "DEMUR-1")
        # Arrived 10 days ago; default free demurrage is 5 → overdue.
        await _set_vessel_ata(bid, date.today() - timedelta(days=10))

        async with TestSession() as db:
            alerted = await DemurrageService.run(db)
            await db.commit()

        assert alerted >= 1
        assert await _count_notifications(bid, NotificationType.DEMURRAGE_WARNING) >= 1

    async def test_within_free_time_no_alert(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, _ = await advance_to(client, h, "in_transit", "DEMUR-2")
        # Arrived today; 5 free days, 2-day lead → 5 days left, no alert.
        await _set_vessel_ata(bid, date.today())

        async with TestSession() as db:
            alerted = await DemurrageService.run(db)
            await db.commit()

        assert alerted == 0

    async def test_demurrage_dedup_same_day(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, _ = await advance_to(client, h, "in_transit", "DEMUR-3")
        await _set_vessel_ata(bid, date.today() - timedelta(days=10))

        async with TestSession() as db:
            await DemurrageService.run(db)
            await db.commit()
        first = await _count_notifications(bid, NotificationType.DEMURRAGE_WARNING)

        async with TestSession() as db:
            alerted2 = await DemurrageService.run(db)
            await db.commit()

        assert alerted2 == 0  # deduped for the day
        assert await _count_notifications(bid, NotificationType.DEMURRAGE_WARNING) == first
