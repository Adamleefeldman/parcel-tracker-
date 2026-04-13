"""
Idempotency key tests.

Validates the ``require_idempotency`` FastAPI dependency on the invoice and
payment POST endpoints.  Missing header → 400.  Duplicate key → cached
response returned without creating a second resource.
"""

import uuid

from httpx import AsyncClient

from tests.integration.conftest import advance_to


class TestIdempotencyRequired:
    """Requests without an Idempotency-Key header are rejected."""

    async def test_invoice_missing_key_returns_400(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "po_submitted", ref="IDEM-INV-400")

        r = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json={
                "invoice_number": "INV-NOKEY",
                "invoice_date": "2026-01-15",
                "value": "10000.00",
                "currency": "USD",
            },
            headers=h,  # no Idempotency-Key
        )
        assert r.status_code == 400
        assert "Idempotency-Key" in r.json()["detail"]

    async def test_payment_missing_key_returns_400(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "invoice_received", ref="IDEM-PAY-400")

        r = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json={
                "swift_ref": "SW-NOKEY",
                "payment_date": "2026-01-20",
                "amount": "5000.00",
                "currency": "USD",
                "payment_type": "partial",
            },
            headers=h,  # no Idempotency-Key
        )
        assert r.status_code == 400
        assert "Idempotency-Key" in r.json()["detail"]


class TestIdempotencyBehaviour:
    """Duplicate keys return cached responses; different keys create separate resources."""

    async def test_duplicate_invoice_key_returns_cached_response(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "po_submitted", ref="IDEM-INV-DUP")
        key = str(uuid.uuid4())

        body = {
            "invoice_number": "INV-DUP",
            "invoice_date": "2026-01-15",
            "value": "10000.00",
            "currency": "USD",
        }

        r1 = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r1.status_code == 200

        # Same key — should return cached response, not create a second invoice
        r2 = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]

    async def test_duplicate_payment_key_returns_cached_response(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "invoice_received", ref="IDEM-PAY-DUP")
        key = str(uuid.uuid4())

        body = {
            "swift_ref": "SW-DUP",
            "payment_date": "2026-01-20",
            "amount": "5000.00",
            "currency": "USD",
            "payment_type": "partial",
        }

        r1 = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]

    async def test_different_keys_create_separate_payments(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "invoice_received", ref="IDEM-PAY-SEP")

        r1 = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json={
                "swift_ref": "SW-A",
                "payment_date": "2026-01-20",
                "amount": "3000.00",
                "currency": "USD",
                "payment_type": "partial",
            },
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json={
                "swift_ref": "SW-B",
                "payment_date": "2026-01-21",
                "amount": "3000.00",
                "currency": "USD",
                "payment_type": "partial",
            },
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r2.status_code == 200
        assert r1.json()["id"] != r2.json()["id"]
