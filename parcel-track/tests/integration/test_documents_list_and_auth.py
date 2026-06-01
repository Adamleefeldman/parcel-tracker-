"""
Tests for the documents list endpoint (``GET /documents``) and the
booking-scoped authorization added to all four document endpoints.

The autouse ``mock_storage_service`` fixture (conftest.py) mocks the storage
calls, so ``upload-url`` / ``confirm`` / ``download-url`` succeed without real
R2 access. These tests focus on the access gate and the list contract, not on
storage mechanics.
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.enums import DocumentEntityType
from tests.integration.conftest import (
    TestSession,
    _add_member,
    advance_to,
    token_to_user_id,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _confirm_doc(
    client: AsyncClient, h: dict, entity_type: str, entity_id: str, file_name: str = "d.pdf"
):
    return await client.post(
        "/api/v1/documents/confirm",
        params={"entity_type": entity_type, "entity_id": entity_id},
        json={"file_key": "k.pdf", "file_name": file_name, "mime_type": "application/pdf"},
        headers=h,
    )


async def _insert_docs(entity_type: DocumentEntityType, entity_id: str, uploaded_by: str, n: int):
    """Insert ``n`` Document rows with strictly increasing uploaded_at so the
    newest-first ordering is deterministic (SQLite second-resolution
    func.now() would otherwise tie)."""
    from app.db.models import Document

    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with TestSession() as db:
        for i in range(n):
            db.add(
                Document(
                    uploaded_by=uuid.UUID(uploaded_by),
                    entity_type=entity_type,
                    entity_id=uuid.UUID(entity_id),
                    file_key=f"key-{i}.pdf",
                    file_name=f"doc-{i}.pdf",
                    mime_type="application/pdf",
                    file_size_bytes=100 + i,
                    uploaded_at=base + timedelta(hours=i),
                )
            )
        await db.commit()


# ── List endpoint ─────────────────────────────────────────────────────────────


class TestDocumentList:
    async def test_returns_entity_docs_newest_first(self, client: AsyncClient, admin_token: str):
        h = _auth(admin_token)
        bid, _ = await advance_to(client, h, "bl_issued", ref="DOC-LIST-ORDER")
        bl = (await client.get(f"/api/v1/bookings/{bid}/bl", headers=h)).json()
        bl_id = bl["id"]

        await _insert_docs(
            DocumentEntityType.BILL_OF_LADING, bl_id, token_to_user_id(admin_token), 3
        )

        r = await client.get(
            "/api/v1/documents",
            params={"entity_type": "bill_of_lading", "entity_id": bl_id},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        body = r.json()
        assert body["total"] == 3
        names = [item["file_name"] for item in body["items"]]
        # uploaded_at desc → doc-2 (newest) first.
        assert names == ["doc-2.pdf", "doc-1.pdf", "doc-0.pdf"]
        # List items carry uploaded_by and omit download_url.
        assert all("uploaded_by" in item for item in body["items"])
        assert all("download_url" not in item for item in body["items"])

    async def test_pagination(self, client: AsyncClient, admin_token: str):
        h = _auth(admin_token)
        bid, _ = await advance_to(client, h, "bl_issued", ref="DOC-LIST-PAGE")
        bl_id = (await client.get(f"/api/v1/bookings/{bid}/bl", headers=h)).json()["id"]
        await _insert_docs(
            DocumentEntityType.BILL_OF_LADING, bl_id, token_to_user_id(admin_token), 3
        )

        r = await client.get(
            "/api/v1/documents",
            params={"entity_type": "bill_of_lading", "entity_id": bl_id, "limit": 2, "offset": 0},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["limit"] == 2
        assert body["offset"] == 0
        # Newest two.
        assert [i["file_name"] for i in body["items"]] == ["doc-2.pdf", "doc-1.pdf"]

    async def test_empty_when_none(self, client: AsyncClient, admin_token: str):
        h = _auth(admin_token)
        bid, _ = await advance_to(client, h, "bl_issued", ref="DOC-LIST-EMPTY")
        bl_id = (await client.get(f"/api/v1/bookings/{bid}/bl", headers=h)).json()["id"]

        r = await client.get(
            "/api/v1/documents",
            params={"entity_type": "bill_of_lading", "entity_id": bl_id},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        assert r.json() == {"items": [], "total": 0, "offset": 0, "limit": 50}

    async def test_404_unknown_entity(self, client: AsyncClient, admin_token: str):
        h = _auth(admin_token)
        r = await client.get(
            "/api/v1/documents",
            params={"entity_type": "bill_of_lading", "entity_id": str(uuid.uuid4())},
            headers=h,
        )
        assert r.status_code == 404, r.json()

    async def test_invalid_entity_type_422(self, client: AsyncClient, admin_token: str):
        h = _auth(admin_token)
        r = await client.get(
            "/api/v1/documents",
            params={"entity_type": "booking", "entity_id": str(uuid.uuid4())},
            headers=h,
        )
        # entity_type is a DocumentEntityType enum query param — bad value 422s.
        assert r.status_code == 422, r.json()

    async def test_403_for_non_member(
        self, client: AsyncClient, admin_token: str, customer_token: str
    ):
        h = _auth(admin_token)
        bid, _ = await advance_to(client, h, "bl_issued", ref="DOC-LIST-403")
        bl_id = (await client.get(f"/api/v1/bookings/{bid}/bl", headers=h)).json()["id"]

        r = await client.get(
            "/api/v1/documents",
            params={"entity_type": "bill_of_lading", "entity_id": bl_id},
            headers=_auth(customer_token),  # not a member of the booking
        )
        assert r.status_code == 403, r.json()


# ── confirm entity_type validation ────────────────────────────────────────────


class TestConfirmEntityTypeValidation:
    async def test_invalid_entity_type_422(self, client: AsyncClient, admin_token: str):
        h = _auth(admin_token)
        # entity_type is a DocumentEntityType enum query param — a bad value is
        # rejected at the FastAPI boundary with 422, before any service call.
        r = await _confirm_doc(client, h, "booking", str(uuid.uuid4()))
        assert r.status_code == 422, r.json()


# ── uploaded_by exposure ──────────────────────────────────────────────────────


class TestUploadedByExposed:
    async def test_confirm_returns_uploaded_by(self, client: AsyncClient, admin_token: str):
        h = _auth(admin_token)
        _bid, ctx = await advance_to(client, h, "po_submitted", ref="DOC-UPLOADED-BY")
        po_id = ctx["po_id"]

        r = await _confirm_doc(client, h, "purchase_order", po_id)
        assert r.status_code == 200, r.json()
        assert r.json()["uploaded_by"] == token_to_user_id(admin_token)


# ── Auth gating across all four endpoints ─────────────────────────────────────


async def _assert_gating(
    client: AsyncClient,
    entity_type: str,
    entity_id: str,
    member_token: str,
    nonmember_token: str,
):
    """member passes, non-member 403 on list / upload-url / confirm / download-url."""
    member_h = _auth(member_token)
    nonmember_h = _auth(nonmember_token)

    # 1. list
    assert (
        await client.get(
            "/api/v1/documents",
            params={"entity_type": entity_type, "entity_id": entity_id},
            headers=member_h,
        )
    ).status_code == 200
    assert (
        await client.get(
            "/api/v1/documents",
            params={"entity_type": entity_type, "entity_id": entity_id},
            headers=nonmember_h,
        )
    ).status_code == 403

    # 2. upload-url
    upload_body = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "file_name": "x.pdf",
        "mime_type": "application/pdf",
    }
    assert (
        await client.post("/api/v1/documents/upload-url", json=upload_body, headers=member_h)
    ).status_code == 200
    assert (
        await client.post("/api/v1/documents/upload-url", json=upload_body, headers=nonmember_h)
    ).status_code == 403

    # 3. confirm — non-member blocked before any write; member creates a doc.
    assert (await _confirm_doc(client, nonmember_h, entity_type, entity_id)).status_code == 403
    confirmed = await _confirm_doc(client, member_h, entity_type, entity_id)
    assert confirmed.status_code == 200, confirmed.json()
    doc_id = confirmed.json()["id"]

    # 4. download-url for the just-created doc.
    assert (
        await client.get(f"/api/v1/documents/{doc_id}/download-url", headers=member_h)
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/documents/{doc_id}/download-url", headers=nonmember_h)
    ).status_code == 403


class TestDocumentAuthGating:
    async def test_purchase_order(
        self,
        client: AsyncClient,
        admin_token: str,
        uk_agent_token: str,
        customer_token: str,
    ):
        h = _auth(admin_token)
        bid, ctx = await advance_to(client, h, "po_submitted", ref="DOC-GATE-PO")
        await _add_member(client, admin_token, bid, uk_agent_token)
        await _assert_gating(client, "purchase_order", ctx["po_id"], uk_agent_token, customer_token)

    async def test_bill_of_lading(
        self,
        client: AsyncClient,
        admin_token: str,
        uk_agent_token: str,
        customer_token: str,
    ):
        h = _auth(admin_token)
        bid, _ = await advance_to(client, h, "bl_issued", ref="DOC-GATE-BL")
        bl_id = (await client.get(f"/api/v1/bookings/{bid}/bl", headers=h)).json()["id"]
        await _add_member(client, admin_token, bid, uk_agent_token)
        await _assert_gating(client, "bill_of_lading", bl_id, uk_agent_token, customer_token)

    async def test_supplier_payment(
        self,
        client: AsyncClient,
        admin_token: str,
        uk_agent_token: str,
        customer_token: str,
    ):
        h = _auth(admin_token)
        bid, _ = await advance_to(client, h, "payment_confirmed", ref="DOC-GATE-PAY")
        detail = (await client.get(f"/api/v1/bookings/{bid}", headers=h)).json()
        payment_id = detail["payments"][0]["id"]
        await _add_member(client, admin_token, bid, uk_agent_token)
        await _assert_gating(client, "payment", payment_id, uk_agent_token, customer_token)

    async def test_admin_bypasses_without_membership(
        self, client: AsyncClient, admin_token: str, second_admin_token: str
    ):
        """A second admin with no BookingUser row still passes the gate."""
        h = _auth(admin_token)
        _bid, ctx = await advance_to(client, h, "po_submitted", ref="DOC-GATE-ADMIN")
        r = await client.get(
            "/api/v1/documents",
            params={"entity_type": "purchase_order", "entity_id": ctx["po_id"]},
            headers=_auth(second_admin_token),
        )
        assert r.status_code == 200, r.json()
