"""
Idempotency key tests.

Validates the ``require_idempotency`` FastAPI dependency on invoice, payment,
vessel-update, customs-note, delivery-schedule, and delivery-status endpoints.
Missing header → 400.  Duplicate key → cached response returned without
re-executing the handler.
"""

import uuid

from httpx import AsyncClient

from tests.integration.conftest import advance_to


class TestIdempotencyRequired:
    """Requests without an Idempotency-Key header are rejected."""

    async def test_invoice_missing_key_returns_400(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        _sid, ctx = await advance_to(client, h, "po_submitted", ref="IDEM-INV-400")

        r = await client.post(
            f"/api/v1/purchase-orders/{ctx['po_id']}/invoice",
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
        _sid, ctx = await advance_to(client, h, "invoice_received", ref="IDEM-PAY-400")

        r = await client.post(
            f"/api/v1/invoices/{ctx['invoice_id']}/supplier-payments",
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
        _sid, ctx = await advance_to(client, h, "po_submitted", ref="IDEM-INV-DUP")
        key = str(uuid.uuid4())

        body = {
            "invoice_number": "INV-DUP",
            "invoice_date": "2026-01-15",
            "value": "10000.00",
            "currency": "USD",
        }

        r1 = await client.post(
            f"/api/v1/purchase-orders/{ctx['po_id']}/invoice",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r1.status_code == 200

        # Same key — should return cached response, not create a second invoice
        r2 = await client.post(
            f"/api/v1/purchase-orders/{ctx['po_id']}/invoice",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]

    async def test_duplicate_payment_key_returns_cached_response(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        _sid, ctx = await advance_to(client, h, "invoice_received", ref="IDEM-PAY-DUP")
        key = str(uuid.uuid4())

        body = {
            "swift_ref": "SW-DUP",
            "payment_date": "2026-01-20",
            "amount": "5000.00",
            "currency": "USD",
            "payment_type": "partial",
        }

        r1 = await client.post(
            f"/api/v1/invoices/{ctx['invoice_id']}/supplier-payments",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/invoices/{ctx['invoice_id']}/supplier-payments",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]

    async def test_different_keys_create_separate_payments(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        _sid, ctx = await advance_to(client, h, "invoice_received", ref="IDEM-PAY-SEP")

        r1 = await client.post(
            f"/api/v1/invoices/{ctx['invoice_id']}/supplier-payments",
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
            f"/api/v1/invoices/{ctx['invoice_id']}/supplier-payments",
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

    async def test_duplicate_vessel_update_key_returns_cached_response(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "in_transit", ref="IDEM-VU-DUP")
        key = str(uuid.uuid4())

        body = {"status": "in_transit", "current_position_note": "Bay of Biscay"}

        r1 = await client.post(
            f"/api/v1/bookings/{sid}/vessel/updates",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/bookings/{sid}/vessel/updates",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r2.status_code == 200
        # Same vessel ID returned — only one update row created
        assert r1.json()["id"] == r2.json()["id"]

    async def test_duplicate_customs_note_key_returns_cached_response(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await advance_to(client, h, "in_transit", ref="IDEM-CN-DUP")
        cid = ctx["container_ids"][0]

        # Create a customs record so the note endpoint has something to attach to
        r = await client.put(
            f"/api/v1/bookings/{sid}/containers/{cid}/customs",
            json={"status": "examination", "hold_reason": "Random inspection"},
            headers=h,
        )
        assert r.status_code == 200

        key = str(uuid.uuid4())
        body = {"note": "Hold for inspection"}

        r1 = await client.post(
            f"/api/v1/bookings/{sid}/containers/{cid}/customs/notes",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/bookings/{sid}/containers/{cid}/customs/notes",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    async def test_duplicate_schedule_delivery_key_returns_cached_response(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await advance_to(client, h, "cleared", ref="IDEM-DS-DUP")
        cid = ctx["container_ids"][0]

        # Create a delivery point
        r = await client.post(
            f"/api/v1/bookings/{sid}/delivery/points",
            json={
                "recipient_name": "Test Recipient",
                "address": "1 Test St, London",
                "contact_name": "Contact",
                "contact_phone": "07700900000",
                "container_ids": [cid],
            },
            headers=h,
        )
        assert r.status_code == 200
        point_id = r.json()["id"]

        key = str(uuid.uuid4())
        body = {
            "delivery_date": "2026-03-01",
            "time_window_start": "08:00",
            "time_window_end": "12:00",
            "haulier": "Test Haulier",
        }

        r1 = await client.post(
            f"/api/v1/bookings/{sid}/delivery/points/{point_id}/schedule",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/bookings/{sid}/delivery/points/{point_id}/schedule",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    async def test_duplicate_delivery_status_update_key_returns_cached_response(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await advance_to(client, h, "cleared", ref="IDEM-DSU-DUP")
        cid = ctx["container_ids"][0]

        r = await client.post(
            f"/api/v1/bookings/{sid}/delivery/points",
            json={
                "recipient_name": "Test Recipient",
                "address": "1 Test St, London",
                "contact_name": "Contact",
                "contact_phone": "07700900000",
                "container_ids": [cid],
            },
            headers=h,
        )
        assert r.status_code == 200
        point_id = r.json()["id"]

        # Schedule it first
        r = await client.post(
            f"/api/v1/bookings/{sid}/delivery/points/{point_id}/schedule",
            json={
                "delivery_date": "2026-03-01",
                "time_window_start": "08:00",
                "time_window_end": "12:00",
                "haulier": "Test Haulier",
            },
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200

        key = str(uuid.uuid4())
        body = {"status": "failed", "failure_reason": "No access"}

        r1 = await client.patch(
            f"/api/v1/bookings/{sid}/delivery/points/{point_id}/status",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r1.status_code == 200

        r2 = await client.patch(
            f"/api/v1/bookings/{sid}/delivery/points/{point_id}/status",
            json=body,
            headers={**h, "Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r1.json() == r2.json()
