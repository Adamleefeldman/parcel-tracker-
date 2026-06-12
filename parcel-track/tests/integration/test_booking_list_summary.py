"""Booking list-card summary fields (backend half of mobile Phase 11).

GET /bookings (and the detail route, since BookingDetailOut extends
BookingOut) carries six additive summary fields for the mobile list cards:
po_count, container_count, vessel_name, eta, port_of_discharge,
product_summary. Field names are a pinned contract with the mobile client.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import BillOfLading, Container
from tests.integration.conftest import TestSession, advance_to

LIST_URL = "/api/v1/bookings"


# ── Seed helpers ────────────────────────────────────────────────────────────────


async def _add_po(
    client: AsyncClient, h: dict, booking_id: str, po_number: str, product: str
) -> None:
    """Create a standalone PO and link it to the booking."""
    r = await client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": po_number,
            "po_date": "2026-01-12",
            "product_description": product,
            "quantity": "100",
            "quantity_unit": "boxes",
            "total_value": "10000.00",
            "currency": "USD",
        },
        headers=h,
    )
    assert r.status_code == 200, f"create PO failed: {r.json()}"
    r = await client.post(
        f"/api/v1/bookings/{booking_id}/purchase-orders",
        json={"purchase_order_id": r.json()["id"]},
        headers=h,
    )
    assert r.status_code == 200, f"link PO failed: {r.json()}"


async def _add_container(booking_id: str, container_number: str) -> None:
    """Insert an extra container under the booking's BL directly in the DB."""
    async with TestSession() as db:
        bl = (
            await db.execute(
                select(BillOfLading).where(BillOfLading.booking_id == uuid.UUID(booking_id))
            )
        ).scalar_one()
        db.add(Container(bl_id=bl.id, container_number=container_number))
        await db.commit()


async def _list_row(client: AsyncClient, h: dict, booking_id: str) -> dict:
    resp = await client.get(LIST_URL, headers=h)
    assert resp.status_code == 200
    return next(item for item in resp.json()["items"] if item["id"] == booking_id)


# ── Tests ───────────────────────────────────────────────────────────────────────


class TestBookingListSummary:
    async def test_rich_booking_all_fields(self, client: AsyncClient, admin_token: str):
        """2 POs + BL + 3 containers + vessel → all six fields populated."""
        h = {"Authorization": f"Bearer {admin_token}"}
        # in_transit: PO "Tiles", BL (felixstowe) with 2 containers, vessel
        # "Test Vessel" departed with eta 2026-02-14.
        bid, _ctx = await advance_to(client, h, "in_transit", "SUM-RICH")
        await _add_po(client, h, bid, "PO-SUM-RICH-2", "Pepsi 330ml")
        await _add_container(bid, "SUMU0000001")

        row = await _list_row(client, h, bid)
        assert row["po_count"] == 2
        assert row["container_count"] == 3
        assert row["vessel_name"] == "Test Vessel"
        assert row["eta"] == "2026-02-14"
        assert row["port_of_discharge"] == "felixstowe"
        # PO-creation order: the advance_to PO ("Tiles") came first.
        assert row["product_summary"] == "Tiles + Pepsi 330ml"

    async def test_product_summary_caps_at_two_and_dedups(
        self, client: AsyncClient, admin_token: str
    ):
        """4 POs, 3 distinct products → first two joined, '+1 more'; dupes count once."""
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, _ctx = await advance_to(client, h, "po_submitted", "SUM-CAP")
        await _add_po(client, h, bid, "PO-SUM-CAP-2", "Pepsi 330ml")
        await _add_po(client, h, bid, "PO-SUM-CAP-3", "Mirinda 330ml")
        await _add_po(client, h, bid, "PO-SUM-CAP-4", "Tiles")  # duplicate description

        row = await _list_row(client, h, bid)
        assert row["po_count"] == 4
        assert row["product_summary"] == "Tiles + Pepsi 330ml +1 more"

    async def test_fresh_booking_zero_counts_and_nulls(self, client: AsyncClient, admin_token: str):
        """No POs, no BL → counts 0 and every nullable field None."""
        h = {"Authorization": f"Bearer {admin_token}"}
        r = await client.post("/api/v1/bookings", json={"reference": "SUM-EMPTY"}, headers=h)
        assert r.status_code == 200
        bid = r.json()["id"]

        row = await _list_row(client, h, bid)
        assert row["po_count"] == 0
        assert row["container_count"] == 0
        assert row["vessel_name"] is None
        assert row["eta"] is None
        assert row["port_of_discharge"] is None
        assert row["product_summary"] is None

    async def test_detail_carries_same_fields(self, client: AsyncClient, admin_token: str):
        """BookingDetailOut extends BookingOut — the detail route must populate too."""
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, _ctx = await advance_to(client, h, "in_transit", "SUM-DETAIL")
        await _add_po(client, h, bid, "PO-SUM-DETAIL-2", "7Up 330ml")

        resp = await client.get(f"{LIST_URL}/{bid}", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert body["po_count"] == 2
        assert body["container_count"] == 2
        assert body["vessel_name"] == "Test Vessel"
        assert body["eta"] == "2026-02-14"
        assert body["port_of_discharge"] == "felixstowe"
        assert body["product_summary"] == "Tiles + 7Up 330ml"
