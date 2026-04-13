"""
Customs clearance integration tests.

Covers:
  - PUT  /containers/{id}/customs   — upsert customs record (status, HMRC ref, duty amount)
  - POST /containers/{id}/customs/notes — add a note
  - Clearing container 1 keeps shipment in_transit (container 2 still pending)
  - Clearing container 2 triggers automatic shipment → cleared transition
"""

import pytest
from httpx import AsyncClient

from tests.integration.conftest import TestSession

# ── shared setup helper ────────────────────────────────────────────────────────


async def _build_awaiting_customs_state(client: AsyncClient, token: str) -> tuple[str, str, str]:
    """Drive the full pre-customs workflow.

    Returns (shipment_id, container1_id, container2_id) with both containers
    in AWAITING_CUSTOMS state and the shipment in IN_TRANSIT.
    """
    hdrs = {"Authorization": f"Bearer {token}"}

    # 1. Create shipment
    r = await client.post("/api/v1/shipments", json={"reference": "DAY6-SHIP"}, headers=hdrs)
    assert r.status_code == 200, r.text
    ship_id = r.json()["id"]

    # 2. Create PO
    r = await client.post(
        f"/api/v1/shipments/{ship_id}/po",
        headers=hdrs,
        json={
            "po_number": "PO-001",
            "po_date": "2026-01-10",
            "product_description": "Industrial widgets",
            "quantity": "100",
            "quantity_unit": "units",
            "total_value": "10000.00",
            "currency": "USD",
        },
    )
    assert r.status_code == 200, r.text
    po_id = r.json()["id"]

    # 3. Seed a Document row directly (bypasses S3)
    async with TestSession() as db:
        import uuid

        from sqlalchemy import select

        from app.core.enums import DocumentEntityType
        from app.db.models import Document, User

        admin = (await db.execute(select(User).where(User.email == "admin@test.com"))).scalar_one()
        db.add(
            Document(
                uploaded_by=admin.id,
                entity_type=DocumentEntityType.PURCHASE_ORDER,
                entity_id=uuid.UUID(po_id),
                file_key="fake/po.pdf",
                file_name="po.pdf",
                mime_type="application/pdf",
            )
        )
        await db.commit()

    # 4. Submit PO
    r = await client.patch(f"/api/v1/shipments/{ship_id}/po/{po_id}/submit", headers=hdrs)
    assert r.status_code == 200, r.text

    # 5. Create invoice (matches PO value — no discrepancy flag)
    r = await client.post(
        f"/api/v1/shipments/{ship_id}/invoice",
        headers={**hdrs, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "invoice_number": "INV-001",
            "invoice_date": "2026-01-15",
            "value": "10000.00",
            "currency": "USD",
        },
    )
    assert r.status_code == 200, r.text

    # 6. Confirm payment
    r = await client.post(
        f"/api/v1/shipments/{ship_id}/payments",
        headers={**hdrs, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "swift_ref": "SWIFT001",
            "payment_date": "2026-01-20",
            "amount": "10000.00",
            "currency": "USD",
            "payment_type": "full",
        },
    )
    assert r.status_code == 200, r.text

    # 7. Upload BL with two containers
    r = await client.post(
        f"/api/v1/shipments/{ship_id}/bl",
        headers=hdrs,
        json={
            "bl_number": "BL-001",
            "bl_date": "2026-02-01",
            "shipper_name": "Shipper Co",
            "consignee_name": "Consignee Ltd",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "Felixstowe",
            "commodity_description": "Industrial widgets",
            "gross_weight_kg": "5000.00",
            "containers": [
                {"container_number": "ABCD1234567"},
                {"container_number": "ABCD7654321"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    containers = r.json()["containers"]
    c1_id = containers[0]["id"]
    c2_id = containers[1]["id"]

    # 8. Assign vessel
    r = await client.post(
        f"/api/v1/shipments/{ship_id}/vessel",
        headers=hdrs,
        json={
            "vessel_name": "MV Tanger",
            "shipping_line": "Maersk",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "Felixstowe",
        },
    )
    assert r.status_code == 200, r.text

    # 9. Confirm departure → IN_TRANSIT
    r = await client.patch(
        f"/api/v1/shipments/{ship_id}/vessel/depart",
        headers=hdrs,
        json={
            "atd": "2026-02-05",
            "eta": "2026-03-01",
        },
    )
    assert r.status_code == 200, r.text

    # 10. Record vessel arrival → containers → AWAITING_CUSTOMS
    r = await client.post(
        f"/api/v1/shipments/{ship_id}/vessel/updates",
        headers=hdrs,
        json={
            "status": "arrived",
            "current_position_note": "Arrived at Felixstowe",
        },
    )
    assert r.status_code == 200, r.text

    return ship_id, c1_id, c2_id


class TestCustomsClearance:
    @pytest.mark.asyncio
    async def test_upsert_customs_record(self, client: AsyncClient, admin_token: str):
        ship_id, c1_id, _ = await _build_awaiting_customs_state(client, admin_token)
        hdrs = {"Authorization": f"Bearer {admin_token}"}
        base = f"/api/v1/shipments/{ship_id}/containers/{c1_id}/customs"

        # Initial upsert — creates the record
        r = await client.put(
            base,
            headers=hdrs,
            json={
                "status": "submitted",
                "hmrc_ref": "HMRC-2026-001",
                "duty_paid": "1500.00",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "submitted"
        assert data["hmrc_ref"] == "HMRC-2026-001"
        assert float(data["duty_paid"]) == 1500.00

        # Second upsert — updates the existing record
        r = await client.put(
            base,
            headers=hdrs,
            json={
                "status": "submitted",
                "hmrc_ref": "HMRC-2026-002",
                "duty_paid": "2000.00",
            },
        )
        assert r.status_code == 200, r.text
        data2 = r.json()
        assert data2["id"] == data["id"]  # same record
        assert data2["hmrc_ref"] == "HMRC-2026-002"
        assert float(data2["duty_paid"]) == 2000.00

    @pytest.mark.asyncio
    async def test_add_customs_note(self, client: AsyncClient, admin_token: str):
        ship_id, c1_id, _ = await _build_awaiting_customs_state(client, admin_token)
        hdrs = {"Authorization": f"Bearer {admin_token}"}
        customs_url = f"/api/v1/shipments/{ship_id}/containers/{c1_id}/customs"

        # Cannot add note before customs record exists
        r = await client.post(f"{customs_url}/notes", headers=hdrs, json={"note": "Too early"})
        assert r.status_code == 404

        # Create customs record first
        r = await client.put(customs_url, headers=hdrs, json={"status": "submitted"})
        assert r.status_code == 200, r.text

        # Now add note
        r = await client.post(
            f"{customs_url}/notes",
            headers=hdrs,
            json={"note": "Hold released pending duty payment confirmation"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["message"] == "Note added"

    @pytest.mark.asyncio
    async def test_clear_first_container_blocks_shipment(
        self, client: AsyncClient, admin_token: str
    ):
        ship_id, c1_id, _ = await _build_awaiting_customs_state(client, admin_token)
        hdrs = {"Authorization": f"Bearer {admin_token}"}

        # Clear container 1
        r = await client.put(
            f"/api/v1/shipments/{ship_id}/containers/{c1_id}/customs",
            headers=hdrs,
            json={
                "status": "cleared",
                "clearance_date": "2026-03-02",
                "hmrc_ref": "HMRC-2026-001",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cleared"

        # Shipment must still be in_transit — container 2 is not cleared
        r = await client.get(f"/api/v1/shipments/{ship_id}", headers=hdrs)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_transit"

    @pytest.mark.asyncio
    async def test_clear_both_containers_clears_shipment(
        self, client: AsyncClient, admin_token: str
    ):
        ship_id, c1_id, c2_id = await _build_awaiting_customs_state(client, admin_token)
        hdrs = {"Authorization": f"Bearer {admin_token}"}

        # Clear container 1
        r = await client.put(
            f"/api/v1/shipments/{ship_id}/containers/{c1_id}/customs",
            headers=hdrs,
            json={"status": "cleared", "clearance_date": "2026-03-02"},
        )
        assert r.status_code == 200, r.text

        # Shipment still blocked
        r = await client.get(f"/api/v1/shipments/{ship_id}", headers=hdrs)
        assert r.json()["status"] == "in_transit"

        # Clear container 2
        r = await client.put(
            f"/api/v1/shipments/{ship_id}/containers/{c2_id}/customs",
            headers=hdrs,
            json={"status": "cleared", "clearance_date": "2026-03-02"},
        )
        assert r.status_code == 200, r.text

        # All containers cleared → shipment auto-transitions to cleared
        r = await client.get(f"/api/v1/shipments/{ship_id}", headers=hdrs)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cleared"
