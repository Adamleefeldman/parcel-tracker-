"""Integration tests for the money-risk read endpoint (mobile Phase 10).

`GET /api/v1/money-risk` aggregates three read-only sections:
  * A/R aging  — full sale-value exposure of unbanked containers, bucketed by age.
  * Demurrage  — whole-day countdown per arrived container.
  * Disputes   — acknowledged vs unacknowledged counts.

The endpoint aggregates globally; each test runs against a fresh DB
(`setup_db` drops/creates per test), so only the rows a test seeds exist.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.enums import ContainerLifecycleStatus
from app.db.models import BillOfLading, Booking, Container, Vessel
from tests.integration.conftest import TestSession, advance_to

URL = "/api/v1/money-risk"


# ── Seed helpers ────────────────────────────────────────────────────────────────


async def _set_container(
    container_id: str,
    *,
    lifecycle: ContainerLifecycleStatus,
    days_aged: int = 0,
    sale_price_total: str | None = None,
    acknowledged: bool = False,
) -> None:
    values: dict = {
        "lifecycle_status": lifecycle,
        "updated_at": datetime.now(UTC) - timedelta(days=days_aged),
    }
    if sale_price_total is not None:
        values["sale_price_total"] = Decimal(sale_price_total)
    if acknowledged:
        values["dispute_acknowledged_at"] = datetime.now(UTC)
    async with TestSession() as db:
        await db.execute(
            update(Container).where(Container.id == uuid.UUID(container_id)).values(**values)
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


async def _set_booking_demurrage(
    booking_id: str, *, free_days: int | None = None, rate: str | None = None
) -> None:
    async with TestSession() as db:
        values: dict = {}
        if free_days is not None:
            values["free_days_demurrage"] = free_days
        if rate is not None:
            values["demurrage_rate_gbp_after"] = Decimal(rate)
        await db.execute(
            update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(**values)
        )
        await db.commit()


def _bucket(summary: dict, label: str) -> dict:
    return next(b for b in summary["ar_aging"]["buckets"] if b["label"] == label)


# ── A/R aging ────────────────────────────────────────────────────────────────────


class TestARaging:
    async def test_buckets_totals_and_exclusions(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        _bid_a, ctx_a = await advance_to(client, h, "bl_issued", "MR-AR-A")
        _bid_b, ctx_b = await advance_to(client, h, "bl_issued", "MR-AR-B")

        # Booking A: one in 0-14, one in 15-30.
        await _set_container(
            ctx_a["container_ids"][0],
            lifecycle=ContainerLifecycleStatus.DELIVERED,
            days_aged=5,
            sale_price_total="100.00",
        )
        await _set_container(
            ctx_a["container_ids"][1],
            lifecycle=ContainerLifecycleStatus.PAID,
            days_aged=20,
            sale_price_total="200.00",
        )
        # Booking B: one in 31-60 with NULL price (counts, amount 0); one BANKED (excluded).
        await _set_container(
            ctx_b["container_ids"][0],
            lifecycle=ContainerLifecycleStatus.INVOICED,
            days_aged=45,
            sale_price_total=None,
        )
        await _set_container(
            ctx_b["container_ids"][1],
            lifecycle=ContainerLifecycleStatus.BANKED,
            days_aged=90,
            sale_price_total="999.00",
        )

        resp = await client.get(URL, headers=h)
        assert resp.status_code == 200, resp.json()
        ar = resp.json()["ar_aging"]

        assert ar["container_count"] == 3  # BANKED excluded
        assert Decimal(ar["total_outstanding"]) == Decimal("300.00")  # NULL price → 0
        assert ar["containers_truncated"] is False

        assert _bucket(resp.json(), "0-14")["count"] == 1
        assert Decimal(_bucket(resp.json(), "0-14")["amount"]) == Decimal("100.00")
        assert _bucket(resp.json(), "15-30")["count"] == 1
        assert Decimal(_bucket(resp.json(), "15-30")["amount"]) == Decimal("200.00")
        assert _bucket(resp.json(), "31-60")["count"] == 1
        assert Decimal(_bucket(resp.json(), "31-60")["amount"]) == Decimal("0")
        assert _bucket(resp.json(), "60+")["count"] == 0

        # Money fields serialise as JSON strings (mobile money helpers depend on this).
        assert isinstance(ar["total_outstanding"], str)
        assert isinstance(_bucket(resp.json(), "0-14")["amount"], str)

    async def test_aged_container_detail_and_sort(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "MR-AR-DET")
        await _set_container(
            ctx["container_ids"][0],
            lifecycle=ContainerLifecycleStatus.DELIVERED,
            days_aged=5,
            sale_price_total="50.00",
        )
        await _set_container(
            ctx["container_ids"][1],
            lifecycle=ContainerLifecycleStatus.DELIVERED,
            days_aged=40,
            sale_price_total="75.00",
        )

        resp = await client.get(URL, headers=h)
        containers = resp.json()["ar_aging"]["containers"]
        assert len(containers) == 2
        # Oldest first.
        assert containers[0]["days_aged"] >= containers[1]["days_aged"]
        assert containers[0]["days_aged"] >= 40
        first = containers[0]
        assert first["booking_id"] == bid
        assert first["lifecycle_status"] == "delivered"
        assert first["sale_price_total"] == "75.00"

    async def test_empty_when_no_unbanked(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.get(URL, headers=h)
        assert resp.status_code == 200
        ar = resp.json()["ar_aging"]
        assert ar["container_count"] == 0
        assert Decimal(ar["total_outstanding"]) == Decimal("0")
        assert ar["containers"] == []


# ── Demurrage ────────────────────────────────────────────────────────────────────


class TestDemurrage:
    async def test_countdown_signs_sort_and_wiring(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        # Booking A: arrived 10 days ago, 5 free days → expired (-5). 2 containers.
        bid_a, _ = await advance_to(client, h, "in_transit", "MR-DEM-A")
        await _set_vessel_ata(bid_a, date.today() - timedelta(days=10))
        await _set_booking_demurrage(bid_a, free_days=5, rate="125.00")
        # Booking B: arrived today, explicit 5 free days → 5 days remaining. 2 containers.
        bid_b, _ = await advance_to(client, h, "in_transit", "MR-DEM-B")
        await _set_vessel_ata(bid_b, date.today())
        await _set_booking_demurrage(bid_b, free_days=5)

        resp = await client.get(URL, headers=h)
        assert resp.status_code == 200, resp.json()
        dem = resp.json()["demurrage"]

        # One row per container: 2 + 2.
        assert len(dem["items"]) == 4
        # Sorted soonest-expiring first.
        remaining = [i["days_remaining"] for i in dem["items"]]
        assert remaining == sorted(remaining)
        assert dem["soonest_days_remaining"] == -5
        # expiring_count = days_remaining <= DEMURRAGE_WARNING_LEAD_DAYS (default 2).
        # The two expired (-5) rows qualify; the two with 5 left do not.
        assert dem["expiring_count"] == 2

        expired_row = dem["items"][0]
        assert expired_row["days_remaining"] == -5
        assert expired_row["expired"] is True
        assert expired_row["free_days"] == 5
        assert expired_row["port_of_discharge"] == "felixstowe"
        assert expired_row["rate_gbp_after"] == "125.00"
        assert expired_row["container_id"]
        assert expired_row["container_number"]

        not_expired = dem["items"][-1]
        assert not_expired["days_remaining"] == 5
        assert not_expired["expired"] is False
        assert not_expired["rate_gbp_after"] is None  # booking B rate unset

    async def test_default_free_days_fallback(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, _ = await advance_to(client, h, "in_transit", "MR-DEM-FB")
        # No free_days_demurrage set on the booking → falls back to default (5).
        await _set_vessel_ata(bid, date.today() - timedelta(days=1))

        resp = await client.get(URL, headers=h)
        dem = resp.json()["demurrage"]
        assert all(i["free_days"] == 5 for i in dem["items"])
        assert all(i["days_remaining"] == 4 for i in dem["items"])  # 5 - 1

    async def test_empty_when_no_arrivals(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        # in_transit but no ata set → not arrived.
        await advance_to(client, h, "in_transit", "MR-DEM-NONE")
        resp = await client.get(URL, headers=h)
        dem = resp.json()["demurrage"]
        assert dem["items"] == []
        assert dem["expiring_count"] == 0
        assert dem["soonest_days_remaining"] is None


# ── Disputes ─────────────────────────────────────────────────────────────────────


class TestDisputes:
    async def test_acknowledged_vs_unacknowledged(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        _bid, ctx = await advance_to(client, h, "bl_issued", "MR-DISP")
        await _set_container(ctx["container_ids"][0], lifecycle=ContainerLifecycleStatus.DISPUTED)
        await _set_container(
            ctx["container_ids"][1],
            lifecycle=ContainerLifecycleStatus.DISPUTED,
            acknowledged=True,
        )

        resp = await client.get(URL, headers=h)
        disputes = resp.json()["disputes"]
        assert disputes["unacknowledged_count"] == 1
        assert disputes["acknowledged_count"] == 1

    async def test_zero_disputes(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.get(URL, headers=h)
        disputes = resp.json()["disputes"]
        assert disputes == {"unacknowledged_count": 0, "acknowledged_count": 0}


# ── Auth ─────────────────────────────────────────────────────────────────────────


class TestAuth:
    async def test_admin_allowed(self, client: AsyncClient, admin_token: str):
        resp = await client.get(URL, headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"ar_aging", "demurrage", "disputes"}

    async def test_uk_agent_allowed(self, client: AsyncClient, uk_agent_token: str):
        resp = await client.get(URL, headers={"Authorization": f"Bearer {uk_agent_token}"})
        assert resp.status_code == 200

    async def test_morocco_agent_forbidden(self, client: AsyncClient, morocco_agent_token: str):
        resp = await client.get(URL, headers={"Authorization": f"Bearer {morocco_agent_token}"})
        assert resp.status_code == 403

    async def test_customer_forbidden(self, client: AsyncClient, customer_token: str):
        resp = await client.get(URL, headers={"Authorization": f"Bearer {customer_token}"})
        assert resp.status_code == 403

    async def test_unauthenticated_rejected(self, client: AsyncClient):
        resp = await client.get(URL)
        assert resp.status_code == 401
