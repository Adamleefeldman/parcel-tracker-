"""
Integrity error tests.

Validates that ``handle_integrity_error`` (WS3) translates unique constraint
violations into clean 409 responses instead of 500s.  All unique constraints
tested here are declared on the SQLAlchemy model metadata (``unique=True``),
so they fire in both SQLite (local) and Postgres (CI).
"""

import uuid

from httpx import AsyncClient

from tests.integration.conftest import advance_to


class TestDuplicateResourceRejection:
    """Duplicate creation of uniquely-constrained resources returns 409."""

    async def test_duplicate_po_number_returns_409(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}

        # Create two separate shipments
        r1 = await client.post("/api/v1/shipments", json={"reference": "DUP-PO-1"}, headers=h)
        r2 = await client.post("/api/v1/shipments", json={"reference": "DUP-PO-2"}, headers=h)
        sid1 = r1.json()["id"]
        sid2 = r2.json()["id"]

        po_body = {
            "po_number": "PO-DUPLICATE",
            "po_date": "2026-01-10",
            "product_description": "Tiles",
            "quantity": "100",
            "quantity_unit": "boxes",
            "total_value": "10000.00",
            "currency": "USD",
        }

        r = await client.post(f"/api/v1/shipments/{sid1}/po", json=po_body, headers=h)
        assert r.status_code == 200

        r = await client.post(f"/api/v1/shipments/{sid2}/po", json=po_body, headers=h)
        assert r.status_code == 409

    async def test_duplicate_invoice_number_returns_409(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}

        sid1, _ = await advance_to(client, h, "po_submitted", ref="DUP-INV-1")
        sid2, _ = await advance_to(client, h, "po_submitted", ref="DUP-INV-2")

        invoice_body = {
            "invoice_number": "INV-DUPLICATE",
            "invoice_date": "2026-01-15",
            "value": "10000.00",
            "currency": "USD",
        }

        r = await client.post(
            f"/api/v1/shipments/{sid1}/invoice",
            json=invoice_body,
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200

        r = await client.post(
            f"/api/v1/shipments/{sid2}/invoice",
            json=invoice_body,
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 409

    async def test_duplicate_bl_number_returns_409(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}

        sid1, _ = await advance_to(client, h, "payment_confirmed", ref="DUP-BL-1")
        sid2, _ = await advance_to(client, h, "payment_confirmed", ref="DUP-BL-2")

        bl_body = {
            "bl_number": "BL-DUPLICATE",
            "bl_date": "2026-01-25",
            "shipper_name": "Shipper",
            "consignee_name": "Consignee",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "Felixstowe",
            "containers": [{"container_number": "DUPL1234567"}],
            "commodity_description": "Tiles",
            "gross_weight_kg": "5000.00",
        }

        r = await client.post(f"/api/v1/shipments/{sid1}/bl", json=bl_body, headers=h)
        assert r.status_code == 200

        r = await client.post(f"/api/v1/shipments/{sid2}/bl", json=bl_body, headers=h)
        assert r.status_code == 409

    async def test_duplicate_shipment_member_returns_409(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}

        # Create shipment and a second user
        r = await client.post("/api/v1/shipments", json={"reference": "DUP-MEMBER"}, headers=h)
        sid = r.json()["id"]

        invite_r = await client.post(
            "/api/v1/auth/invite",
            json={"email": "dup-member@test.com", "role": "customer"},
            headers=h,
        )
        accept_r = await client.post(
            "/api/v1/auth/accept-invite",
            json={
                "token": invite_r.json()["invite_token"],
                "name": "Dup Member",
                "password": "testpass123",
            },
        )
        from jose import jwt as jose_jwt

        user_id = jose_jwt.get_unverified_claims(accept_r.json()["access_token"])["sub"]

        # First add — should succeed
        r = await client.post(
            f"/api/v1/shipments/{sid}/members",
            json={"user_id": user_id},
            headers=h,
        )
        assert r.status_code == 200

        # Duplicate add — should return 409
        r = await client.post(
            f"/api/v1/shipments/{sid}/members",
            json={"user_id": user_id},
            headers=h,
        )
        assert r.status_code == 409
