"""Integration tests for P2.1 — dispute open / acknowledge + COMPLETE precondition."""

import uuid

from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.enums import BookingStatus, ContainerLifecycleStatus
from app.db.models import BillOfLading, Container, User
from app.services.booking_service import BookingService
from tests.integration.conftest import TestSession, advance_to


async def _fetch_admin() -> User:
    async with TestSession() as db:
        result = await db.execute(select(User).where(User.email == "admin@test.com"))
        return result.scalar_one()


async def _bank_all_for_booking(booking_id: str) -> None:
    """Drive every container on a booking to BANKED — leaves only an
    explicitly-disputed container as a blocker to COMPLETE."""
    async with TestSession() as db:
        await db.execute(
            update(Container)
            .where(
                Container.bl_id.in_(
                    select(BillOfLading.id).where(BillOfLading.booking_id == uuid.UUID(booking_id))
                )
            )
            .values(lifecycle_status=ContainerLifecycleStatus.BANKED)
        )
        await db.commit()


class TestOpenDispute:
    async def test_admin_opens_dispute(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "DISP-OPEN-1")
        cid = ctx["container_ids"][0]

        resp = await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "broken seal on arrival"},
            headers=h,
        )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["lifecycle_status"] == "disputed"
        assert body["dispute_reason"] == "broken seal on arrival"
        assert body["disputed_at"] is not None
        assert body["dispute_acknowledged_at"] is None

    async def test_non_admin_cannot_open(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "DISP-OPEN-2")
        cid = ctx["container_ids"][0]
        resp = await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "x"},
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_empty_reason_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "DISP-OPEN-3")
        cid = ctx["container_ids"][0]
        resp = await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "   "},
            headers=h,
        )
        assert resp.status_code == 422

    async def test_unknown_container_404(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, _ = await advance_to(client, h, "bl_issued", "DISP-OPEN-4")
        resp = await client.patch(
            f"/api/v1/bookings/{bid}/containers/{uuid.uuid4()}/dispute",
            json={"reason": "x"},
            headers=h,
        )
        assert resp.status_code == 404


class TestAcknowledgeDispute:
    async def test_ack_sets_timestamp_and_preserves_lifecycle(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "DISP-ACK-1")
        cid = ctx["container_ids"][0]
        await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "wrong product"},
            headers=h,
        )
        resp = await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute/acknowledge",
            json={},
            headers=h,
        )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        # Lifecycle deliberately stays DISPUTED (dispute history preserved).
        assert body["lifecycle_status"] == "disputed"
        assert body["dispute_reason"] == "wrong product"
        assert body["dispute_acknowledged_at"] is not None
        assert body["dispute_acknowledged_by"] is not None

    async def test_ack_on_non_disputed_400(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "DISP-ACK-2")
        cid = ctx["container_ids"][0]
        resp = await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute/acknowledge",
            json={},
            headers=h,
        )
        assert resp.status_code == 400

    async def test_non_admin_cannot_ack(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "DISP-ACK-3")
        cid = ctx["container_ids"][0]
        await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "x"},
            headers=h,
        )
        resp = await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute/acknowledge",
            json={},
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_reopen_clears_previous_ack(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "bl_issued", "DISP-REOPEN")
        cid = ctx["container_ids"][0]
        await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "first issue"},
            headers=h,
        )
        await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute/acknowledge",
            json={},
            headers=h,
        )
        # Re-open: the ack should be wiped.
        resp = await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "second issue"},
            headers=h,
        )
        body = resp.json()
        assert body["dispute_reason"] == "second issue"
        assert body["dispute_acknowledged_at"] is None
        assert body["dispute_acknowledged_by"] is None


class TestCompletePrecondition:
    async def test_unacked_dispute_blocks_complete(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "cleared", "DISP-COMPLETE-1")
        await _bank_all_for_booking(bid)

        # Dispute one container — it leaves BANKED for DISPUTED.
        cid = ctx["container_ids"][0]
        await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "short shipment"},
            headers=h,
        )

        # Attempt the transition directly — precondition must reject.
        admin = await _fetch_admin()
        async with TestSession() as db:
            booking = await BookingService.get(db, uuid.UUID(bid), admin)
            try:
                await BookingService.transition_status(
                    db, booking, BookingStatus.COMPLETE, admin, None
                )
                raise AssertionError("transition should have been blocked")
            except HTTPException as exc:
                assert exc.status_code == 400
                assert "disputed" in exc.detail.lower()

    async def test_acked_dispute_allows_complete(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, ctx = await advance_to(client, h, "cleared", "DISP-COMPLETE-2")
        await _bank_all_for_booking(bid)

        cid = ctx["container_ids"][0]
        await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute",
            json={"reason": "minor damage"},
            headers=h,
        )
        await client.patch(
            f"/api/v1/bookings/{bid}/containers/{cid}/dispute/acknowledge",
            json={},
            headers=h,
        )

        admin = await _fetch_admin()
        async with TestSession() as db:
            booking = await BookingService.get(db, uuid.UUID(bid), admin)
            updated = await BookingService.transition_status(
                db, booking, BookingStatus.COMPLETE, admin, None
            )
            await db.commit()
            assert updated.status == BookingStatus.COMPLETE
