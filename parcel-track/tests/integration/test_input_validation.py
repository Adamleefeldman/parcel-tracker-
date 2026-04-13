"""
Input validation tests.

Validates all Pydantic ``field_validator`` and ``model_validator`` additions
from WS5.  Each test sends invalid input to an HTTP endpoint and asserts a
422 Unprocessable Entity response from FastAPI's automatic validation.
"""

import uuid

from httpx import AsyncClient

from tests.integration.conftest import advance_to

# ── Purchase Order validators ────────────────────────────────────────────────


class TestPOValidation:
    async def test_po_quantity_zero_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "draft", ref="VAL-PO-QTY")
        r = await client.post(
            f"/api/v1/shipments/{sid}/po",
            json={
                "po_number": "PO-VAL-QTY",
                "po_date": "2026-01-10",
                "product_description": "Tiles",
                "quantity": "0",
                "quantity_unit": "boxes",
                "total_value": "10000.00",
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 422

    async def test_po_total_value_negative_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "draft", ref="VAL-PO-VAL")
        r = await client.post(
            f"/api/v1/shipments/{sid}/po",
            json={
                "po_number": "PO-VAL-VAL",
                "po_date": "2026-01-10",
                "product_description": "Tiles",
                "quantity": "100",
                "quantity_unit": "boxes",
                "total_value": "-1",
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 422


# ── Invoice validators ───────────────────────────────────────────────────────


class TestInvoiceValidation:
    async def test_invoice_value_zero_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "po_submitted", ref="VAL-INV-ZERO")
        r = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json={
                "invoice_number": "INV-VAL-ZERO",
                "invoice_date": "2026-01-15",
                "value": "0",
                "currency": "USD",
            },
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 422

    async def test_invoice_due_date_before_invoice_date_rejected(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "po_submitted", ref="VAL-INV-DATE")
        r = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json={
                "invoice_number": "INV-VAL-DATE",
                "invoice_date": "2026-03-01",
                "value": "10000.00",
                "currency": "USD",
                "due_date": "2026-02-01",
            },
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 422


# ── Payment validators ───────────────────────────────────────────────────────


class TestPaymentValidation:
    async def test_payment_amount_zero_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "invoice_received", ref="VAL-PAY-ZERO")
        r = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json={
                "swift_ref": "SW-VAL-ZERO",
                "payment_date": "2026-01-20",
                "amount": "0",
                "currency": "USD",
                "payment_type": "full",
            },
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 422


# ── Bill of Lading validators ────────────────────────────────────────────────


class TestBLValidation:
    async def test_bl_gross_weight_negative_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "payment_confirmed", ref="VAL-BL-WT")
        r = await client.post(
            f"/api/v1/shipments/{sid}/bl",
            json={
                "bl_number": "BL-VAL-WT",
                "bl_date": "2026-01-25",
                "shipper_name": "Shipper",
                "consignee_name": "Consignee",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
                "containers": [{"container_number": "VALW1234567"}],
                "commodity_description": "Tiles",
                "gross_weight_kg": "-5",
            },
            headers=h,
        )
        assert r.status_code == 422

    async def test_bl_empty_containers_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "payment_confirmed", ref="VAL-BL-EMPTY")
        r = await client.post(
            f"/api/v1/shipments/{sid}/bl",
            json={
                "bl_number": "BL-VAL-EMPTY",
                "bl_date": "2026-01-25",
                "shipper_name": "Shipper",
                "consignee_name": "Consignee",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
                "containers": [],
                "commodity_description": "Tiles",
                "gross_weight_kg": "5000.00",
            },
            headers=h,
        )
        assert r.status_code == 422

    async def test_bl_duplicate_containers_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "payment_confirmed", ref="VAL-BL-DUP")
        r = await client.post(
            f"/api/v1/shipments/{sid}/bl",
            json={
                "bl_number": "BL-VAL-DUP",
                "bl_date": "2026-01-25",
                "shipper_name": "Shipper",
                "consignee_name": "Consignee",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
                "containers": [
                    {"container_number": "DUPC1234567"},
                    {"container_number": "DUPC1234567"},
                ],
                "commodity_description": "Tiles",
                "gross_weight_kg": "5000.00",
            },
            headers=h,
        )
        assert r.status_code == 422


# ── Clearing docs validators ─────────────────────────────────────────────────


class TestClearingDocsValidation:
    async def test_clearing_docs_negative_duty_rate_rejected(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "draft", ref="VAL-CLR-RATE")
        r = await client.put(
            f"/api/v1/shipments/{sid}/clearing-docs",
            json={"duty_rate": "-0.5"},
            headers=h,
        )
        assert r.status_code == 422

    async def test_clearing_docs_negative_estimated_duty_vat_rejected(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "draft", ref="VAL-CLR-VAT")
        r = await client.put(
            f"/api/v1/shipments/{sid}/clearing-docs",
            json={"estimated_duty_vat": "-1"},
            headers=h,
        )
        assert r.status_code == 422


# ── Customs validators ───────────────────────────────────────────────────────


class TestCustomsValidation:
    async def test_customs_negative_duty_paid_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await advance_to(client, h, "in_transit", ref="VAL-CUST-DP")
        cid = ctx["container_ids"][0]
        r = await client.put(
            f"/api/v1/shipments/{sid}/containers/{cid}/customs",
            json={"status": "cleared", "clearance_date": "2026-03-01", "duty_paid": "-1"},
            headers=h,
        )
        assert r.status_code == 422


# ── Delivery schedule validators ─────────────────────────────────────────────


class TestDeliveryScheduleValidation:
    async def test_delivery_schedule_invalid_time_format_rejected(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await advance_to(client, h, "cleared", ref="VAL-DEL-FMT")
        cid = ctx["container_ids"][0]

        # Create a delivery point first
        r = await client.post(
            f"/api/v1/shipments/{sid}/delivery/points",
            json={
                "recipient_name": "Recipient",
                "address": "123 Street",
                "contact_name": "Contact",
                "contact_phone": "0123456789",
                "container_ids": [cid],
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        dp_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/shipments/{sid}/delivery/points/{dp_id}/schedule",
            json={
                "delivery_date": "2026-03-15",
                "time_window_start": "7am",
                "time_window_end": "12:00",
                "haulier": "TestHaulier",
            },
            headers=h,
        )
        assert r.status_code == 422

    async def test_delivery_schedule_end_before_start_rejected(
        self, client: AsyncClient, admin_token: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await advance_to(client, h, "cleared", ref="VAL-DEL-ORD")
        cid = ctx["container_ids"][0]

        r = await client.post(
            f"/api/v1/shipments/{sid}/delivery/points",
            json={
                "recipient_name": "Recipient",
                "address": "123 Street",
                "contact_name": "Contact",
                "contact_phone": "0123456789",
                "container_ids": [cid],
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        dp_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/shipments/{sid}/delivery/points/{dp_id}/schedule",
            json={
                "delivery_date": "2026-03-15",
                "time_window_start": "14:00",
                "time_window_end": "09:00",
                "haulier": "TestHaulier",
            },
            headers=h,
        )
        assert r.status_code == 422


# ── Upload validators ────────────────────────────────────────────────────────


class TestUploadValidation:
    async def test_upload_disallowed_mime_type_rejected(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "entity_type": "shipment",
                "entity_id": shipment,
                "file_name": "evil.exe",
                "mime_type": "application/x-executable",
            },
            headers=h,
        )
        assert r.status_code == 422

    async def test_upload_file_too_large_rejected(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "entity_type": "shipment",
                "entity_id": shipment,
                "file_name": "huge.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 60_000_000,
            },
            headers=h,
        )
        assert r.status_code == 422

    async def test_upload_allowed_mime_accepted(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "entity_type": "shipment",
                "entity_id": shipment,
                "file_name": "doc.pdf",
                "mime_type": "application/pdf",
            },
            headers=h,
        )
        assert r.status_code == 200


# ── Password validators ──────────────────────────────────────────────────────


class TestPasswordValidation:
    async def test_short_password_rejected(self, client: AsyncClient, admin_token: str):
        h = {"Authorization": f"Bearer {admin_token}"}

        invite_r = await client.post(
            "/api/v1/auth/invite",
            json={"email": "short-pass@test.com", "role": "customer"},
            headers=h,
        )
        assert invite_r.status_code == 200

        r = await client.post(
            "/api/v1/auth/accept-invite",
            json={
                "token": invite_r.json()["invite_token"],
                "name": "Short Pass",
                "password": "short",
            },
        )
        assert r.status_code == 422
