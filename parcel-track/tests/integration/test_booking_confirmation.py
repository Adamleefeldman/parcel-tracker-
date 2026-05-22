"""Integration tests for P1.2 booking-confirmation fields.

The 9 carrier-confirmation columns are populated via PATCH /bookings/{id} and
surfaced on the GET /bookings/{id} detail response.
"""

from decimal import Decimal

from httpx import AsyncClient


class TestBookingConfirmationFields:
    async def test_patch_sets_and_detail_returns_fields(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.patch(
            f"/api/v1/bookings/{booking}",
            json={
                "free_days_detention": 7,
                "free_days_demurrage": 5,
                "detention_rate_gbp_after": "120.50",
                "demurrage_rate_gbp_after": "200.00",
                "gate_in_cutoff": "2026-06-01T08:00:00Z",
                "empty_return_deadline": "2026-06-20T17:00:00Z",
                "port_of_discharge_terminal": "LGT Berth 3",
                "service_mode": "CY/CY",
            },
            headers=h,
        )
        assert resp.status_code == 200, resp.json()

        body = (await client.get(f"/api/v1/bookings/{booking}", headers=h)).json()
        assert body["free_days_detention"] == 7
        assert body["free_days_demurrage"] == 5
        assert Decimal(str(body["detention_rate_gbp_after"])) == Decimal("120.50")
        assert Decimal(str(body["demurrage_rate_gbp_after"])) == Decimal("200.00")
        assert body["port_of_discharge_terminal"] == "LGT Berth 3"
        assert body["service_mode"] == "CY/CY"
        assert body["gate_in_cutoff"] is not None
        assert body["empty_return_deadline"] is not None

    async def test_fresh_booking_confirmation_fields_are_null(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        body = (await client.get(f"/api/v1/bookings/{booking}", headers=h)).json()
        for field in (
            "gate_in_cutoff",
            "empty_pickup_release",
            "empty_return_deadline",
            "free_days_detention",
            "free_days_demurrage",
            "detention_rate_gbp_after",
            "demurrage_rate_gbp_after",
            "port_of_discharge_terminal",
            "service_mode",
        ):
            assert field in body
            assert body[field] is None

    async def test_partial_patch_leaves_other_fields_untouched(
        self, client: AsyncClient, admin_token: str, booking: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        await client.patch(
            f"/api/v1/bookings/{booking}",
            json={"free_days_detention": 7},
            headers=h,
        )
        await client.patch(
            f"/api/v1/bookings/{booking}",
            json={"service_mode": "CY/CY"},
            headers=h,
        )
        body = (await client.get(f"/api/v1/bookings/{booking}", headers=h)).json()
        assert body["free_days_detention"] == 7  # survived the second PATCH
        assert body["service_mode"] == "CY/CY"
