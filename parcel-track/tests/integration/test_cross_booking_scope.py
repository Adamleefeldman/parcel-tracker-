"""Cross-booking scoping guard (P0-2).

Customer-payment and customs endpoints are nested under
``/bookings/{booking_id}/containers/{container_id}/…`` but historically resolved
the container by id alone — so a caller could pair booking A's path with booking
B's container and write/read across the boundary. Every such endpoint must now
404 when the container does not belong to the booking in the URL, while the
same-booking happy path keeps working.
"""

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import _add_member, advance_to


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _idem(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())}


async def _two_bookings(client: AsyncClient, admin_token: str) -> tuple[str, str, str, str]:
    """Two independent bookings advanced to bl_issued; return (bidA, cA, bidB, cB)."""
    h = _h(admin_token)
    bid_a, ctx_a = await advance_to(client, h, "bl_issued", ref="XBK-A")
    bid_b, ctx_b = await advance_to(client, h, "bl_issued", ref="XBK-B")
    return bid_a, ctx_a["container_ids"][0], bid_b, ctx_b["container_ids"][0]


@pytest.mark.asyncio
async def test_customer_payment_post_rejects_cross_booking_container(
    client: AsyncClient, admin_token: str
):
    bid_a, _c_a, _bid_b, c_b = await _two_bookings(client, admin_token)
    body = {"payment_date": "2026-03-01", "method": "cash", "amount_received": "100.00"}

    # Booking A's URL + booking B's container → 404, not a misfiled payment.
    resp = await client.post(
        f"/api/v1/bookings/{bid_a}/containers/{c_b}/customer-payments",
        json=body,
        headers=_idem(admin_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_customer_payment_post_same_booking_still_works(
    client: AsyncClient, admin_token: str
):
    _bid_a, _c_a, bid_b, c_b = await _two_bookings(client, admin_token)
    body = {"payment_date": "2026-03-01", "method": "cash", "amount_received": "100.00"}

    resp = await client.post(
        f"/api/v1/bookings/{bid_b}/containers/{c_b}/customer-payments",
        json=body,
        headers=_idem(admin_token),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_customs_put_rejects_cross_booking_container(client: AsyncClient, admin_token: str):
    bid_a, _c_a, _bid_b, c_b = await _two_bookings(client, admin_token)

    resp = await client.put(
        f"/api/v1/bookings/{bid_a}/containers/{c_b}/customs",
        json={"status": "cleared", "clearance_date": "2026-03-01"},
        headers=_h(admin_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_customs_put_same_booking_still_works(client: AsyncClient, admin_token: str):
    _bid_a, _c_a, bid_b, c_b = await _two_bookings(client, admin_token)

    # Only one of booking B's two containers clears, so no premature booking
    # transition — this isolates the ownership check from state-machine concerns.
    resp = await client.put(
        f"/api/v1/bookings/{bid_b}/containers/{c_b}/customs",
        json={"status": "cleared", "clearance_date": "2026-03-01"},
        headers=_h(admin_token),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_customs_note_rejects_cross_booking_container(client: AsyncClient, admin_token: str):
    bid_a, _c_a, _bid_b, c_b = await _two_bookings(client, admin_token)

    resp = await client.post(
        f"/api/v1/bookings/{bid_a}/containers/{c_b}/customs/notes",
        json={"note": "should not attach across bookings"},
        headers=_idem(admin_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_customer_payment_reads_do_not_leak_across_bookings(
    client: AsyncClient, admin_token: str, uk_agent_token: str
):
    """A non-admin member of booking A must not read booking B's tranche metadata
    by pairing A's path with B's container."""
    bid_a, _c_a, _bid_b, c_b = await _two_bookings(client, admin_token)
    await _add_member(client, admin_token, bid_a, uk_agent_token)

    list_resp = await client.get(
        f"/api/v1/bookings/{bid_a}/containers/{c_b}/customer-payments",
        headers=_h(uk_agent_token),
    )
    assert list_resp.status_code == 404, list_resp.text

    agg_resp = await client.get(
        f"/api/v1/bookings/{bid_a}/containers/{c_b}/customer-payments/aggregate",
        headers=_h(uk_agent_token),
    )
    assert agg_resp.status_code == 404, agg_resp.text
