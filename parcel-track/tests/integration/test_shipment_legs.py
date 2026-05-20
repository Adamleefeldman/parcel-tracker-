"""Integration tests for the P1.1 multi-leg ShipmentLeg routes.

Covers POST/GET/PATCH under /bookings/{id}/legs, leg_index auto-assignment,
the legs block on the booking detail response, and RBAC.

Fixtures (client, admin_token, booking, role tokens, setup_db) come from
conftest.py.
"""

import uuid

from httpx import AsyncClient


def _decode_user_id(token: str) -> str:
    from jose import jwt

    from app.core.config import get_settings

    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])["sub"]


async def _assign_member(client: AsyncClient, admin_token: str, booking_id: str, user_token: str):
    user_id = _decode_user_id(user_token)
    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/members",
        json={"user_id": user_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Member assignment failed: {resp.json()}"


def _leg_body(**overrides) -> dict:
    body = {
        "vessel_name": "MAERSK NEWARK",
        "voyage_number": "V602E",
        "shipping_line": "Maersk",
        "port_from": "Casablanca",
        "port_to": "Algeciras",
    }
    body.update(overrides)
    return body


async def _post_leg(client: AsyncClient, token: str, booking_id: str, **overrides):
    return await client.post(
        f"/api/v1/bookings/{booking_id}/legs",
        json=_leg_body(**overrides),
        headers={"Authorization": f"Bearer {token}"},
    )


# ── Create ───────────────────────────────────────────────────────────────────


class TestCreateLeg:
    async def test_admin_creates_first_leg_index_1(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        resp = await _post_leg(client, admin_token, booking)
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["leg_index"] == 1
        assert body["vessel_name"] == "MAERSK NEWARK"
        assert body["port_from"] == "Casablanca"
        assert body["booking_id"] == booking

    async def test_legs_auto_increment(self, client: AsyncClient, admin_token: str, booking: str):
        first = await _post_leg(client, admin_token, booking)
        second = await _post_leg(
            client, admin_token, booking, vessel_name="MADRID MAERSK", port_to="London Gateway"
        )
        assert first.json()["leg_index"] == 1
        assert second.json()["leg_index"] == 2

    async def test_explicit_leg_index_respected(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        resp = await _post_leg(client, admin_token, booking, leg_index=7)
        assert resp.status_code == 200
        assert resp.json()["leg_index"] == 7

    async def test_duplicate_leg_index_conflicts(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        await _post_leg(client, admin_token, booking, leg_index=1)
        dup = await _post_leg(client, admin_token, booking, leg_index=1)
        assert dup.status_code == 409

    async def test_create_on_unknown_booking_404(self, client: AsyncClient, admin_token: str):
        resp = await _post_leg(client, admin_token, str(uuid.uuid4()))
        assert resp.status_code == 404


# ── List ─────────────────────────────────────────────────────────────────────


class TestListLegs:
    async def test_list_returns_legs_ordered(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        # Insert out of natural order via explicit indices.
        await _post_leg(client, admin_token, booking, leg_index=2, port_to="London Gateway")
        await _post_leg(client, admin_token, booking, leg_index=1)

        resp = await client.get(
            f"/api/v1/bookings/{booking}/legs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        indices = [leg["leg_index"] for leg in resp.json()]
        assert indices == [1, 2]

    async def test_list_empty_for_fresh_booking(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        resp = await client.get(
            f"/api/v1/bookings/{booking}/legs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ── Update ───────────────────────────────────────────────────────────────────


class TestUpdateLeg:
    async def test_patch_sets_ata(self, client: AsyncClient, admin_token: str, booking: str):
        leg_id = (await _post_leg(client, admin_token, booking)).json()["id"]

        resp = await client.patch(
            f"/api/v1/bookings/{booking}/legs/{leg_id}",
            json={"ata": "2026-05-18"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ata"] == "2026-05-18"
        assert body["vessel_name"] == "MAERSK NEWARK"  # untouched

    async def test_patch_unknown_leg_404(self, client: AsyncClient, admin_token: str, booking: str):
        resp = await client.patch(
            f"/api/v1/bookings/{booking}/legs/{uuid.uuid4()}",
            json={"ata": "2026-05-18"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


# ── Booking detail integration ───────────────────────────────────────────────


class TestBookingDetailLegs:
    async def test_detail_includes_legs_block(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        await _post_leg(client, admin_token, booking)
        await _post_leg(
            client, admin_token, booking, vessel_name="MADRID MAERSK", port_to="London Gateway"
        )

        resp = await client.get(
            f"/api/v1/bookings/{booking}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        legs = resp.json()["legs"]
        assert [leg["leg_index"] for leg in legs] == [1, 2]
        assert legs[1]["port_to"] == "London Gateway"

    async def test_detail_legs_empty_for_fresh_booking(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        resp = await client.get(
            f"/api/v1/bookings/{booking}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.json()["legs"] == []


# ── RBAC ─────────────────────────────────────────────────────────────────────


class TestLegRBAC:
    async def test_morocco_agent_member_can_create(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str, booking: str
    ):
        await _assign_member(client, admin_token, booking, morocco_agent_token)
        resp = await _post_leg(client, morocco_agent_token, booking)
        assert resp.status_code == 200

    async def test_customer_member_cannot_create(
        self, client: AsyncClient, admin_token: str, customer_token: str, booking: str
    ):
        await _assign_member(client, admin_token, booking, customer_token)
        resp = await _post_leg(client, customer_token, booking)
        assert resp.status_code == 403

    async def test_non_member_cannot_read(
        self, client: AsyncClient, morocco_agent_token: str, booking: str
    ):
        resp = await client.get(
            f"/api/v1/bookings/{booking}/legs",
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_customer_member_can_read(
        self, client: AsyncClient, admin_token: str, customer_token: str, booking: str
    ):
        await _assign_member(client, admin_token, booking, customer_token)
        resp = await client.get(
            f"/api/v1/bookings/{booking}/legs",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert resp.status_code == 200
