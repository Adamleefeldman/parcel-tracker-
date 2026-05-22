"""Integration tests for P1.3 — UK port enum + PortTemplate.

Covers the port-template admin routes, the BL `port_of_discharge` enum
validation, and the BL-create → booking port-default inheritance.
"""

from httpx import AsyncClient

from tests.integration.conftest import advance_to


class TestPortTemplateRoutes:
    async def test_admin_upserts_and_lists(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.put(
            "/api/v1/port-templates/felixstowe",
            json={
                "free_days_detention": 7,
                "free_days_demurrage": 5,
                "detention_rate_gbp_after": "100.00",
                "demurrage_rate_gbp_after": "150.00",
            },
            headers=h,
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["port"] == "felixstowe"
        assert resp.json()["free_days_demurrage"] == 5

        listing = await client.get("/api/v1/port-templates", headers=h)
        assert listing.status_code == 200
        assert any(t["port"] == "felixstowe" for t in listing.json())

    async def test_upsert_updates_in_place(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        await client.put(
            "/api/v1/port-templates/tilbury",
            json={"free_days_detention": 3, "free_days_demurrage": 3},
            headers=h,
        )
        resp = await client.put(
            "/api/v1/port-templates/tilbury",
            json={"free_days_detention": 9, "free_days_demurrage": 9},
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["free_days_detention"] == 9
        tilbury = [
            t
            for t in (await client.get("/api/v1/port-templates", headers=h)).json()
            if t["port"] == "tilbury"
        ]
        assert len(tilbury) == 1  # upsert — one row, not two

    async def test_non_admin_cannot_upsert(self, client: AsyncClient, morocco_agent_token: str):
        resp = await client.put(
            "/api/v1/port-templates/tilbury",
            json={"free_days_detention": 3, "free_days_demurrage": 3},
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_invalid_port_path_rejected(self, client: AsyncClient, admin_token: str):
        resp = await client.put(
            "/api/v1/port-templates/atlantis",
            json={"free_days_detention": 3, "free_days_demurrage": 3},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    async def test_negative_free_days_rejected(self, client: AsyncClient, admin_token: str):
        resp = await client.put(
            "/api/v1/port-templates/liverpool",
            json={"free_days_detention": -1, "free_days_demurrage": 3},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422


class TestBLPortEnum:
    async def test_bl_create_rejects_invalid_port(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        bid, _ = await advance_to(client, h, "payment_confirmed", "PORT-BAD")
        resp = await client.post(
            f"/api/v1/bookings/{bid}/bl",
            json={
                "bl_number": "BL-PORT-BAD",
                "bl_date": "2026-01-25",
                "shipper_name": "S",
                "consignee_name": "C",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "atlantis",
                "containers": [{"container_number": "TCKU1230000"}],
                "commodity_description": "Tiles",
                "gross_weight_kg": "5000.00",
            },
            headers=h,
        )
        assert resp.status_code == 422

    async def test_bl_create_inherits_port_template_defaults(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        # Seed the felixstowe template, then drive a booking through BL upload
        # (advance_to uploads the BL with port_of_discharge="felixstowe").
        await client.put(
            "/api/v1/port-templates/felixstowe",
            json={"free_days_detention": 8, "free_days_demurrage": 6},
            headers=h,
        )
        bid, _ = await advance_to(client, h, "bl_issued", "PORT-INHERIT")

        detail = (await client.get(f"/api/v1/bookings/{bid}", headers=h)).json()
        assert detail["free_days_detention"] == 8
        assert detail["free_days_demurrage"] == 6

    async def test_bl_create_does_not_override_set_fields(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        await client.put(
            "/api/v1/port-templates/felixstowe",
            json={"free_days_detention": 8, "free_days_demurrage": 6},
            headers=h,
        )
        # Manually create + advance the booking, setting free_days_demurrage
        # before the BL is uploaded so the template must not clobber it.
        bid, _ = await advance_to(client, h, "payment_confirmed", "PORT-KEEP")
        await client.patch(
            f"/api/v1/bookings/{bid}",
            json={"free_days_demurrage": 99},
            headers=h,
        )
        resp = await client.post(
            f"/api/v1/bookings/{bid}/bl",
            json={
                "bl_number": "BL-PORT-KEEP",
                "bl_date": "2026-01-25",
                "shipper_name": "S",
                "consignee_name": "C",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "felixstowe",
                "containers": [{"container_number": "TCKU9990000"}],
                "commodity_description": "Tiles",
                "gross_weight_kg": "5000.00",
            },
            headers=h,
        )
        assert resp.status_code == 200, resp.json()
        detail = (await client.get(f"/api/v1/bookings/{bid}", headers=h)).json()
        assert detail["free_days_demurrage"] == 99  # preserved
        assert detail["free_days_detention"] == 8  # inherited (was unset)
