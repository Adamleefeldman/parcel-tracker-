"""
Tests for ``POST /documents/confirm`` storage-verification behaviour.

The confirm endpoint HEADs the object in R2 before writing the ``Document``
row. These tests exercise the two failure paths that verification adds:

  * 400 — presigned PUT never succeeded (``StorageObjectNotFound``)
  * 413 — uploaded object exceeds ``MAX_FILE_SIZE_BYTES``

The autouse ``mock_storage_service`` fixture (see ``conftest.py``) already
mocks ``verify_upload`` to return a healthy 1024-byte response. Each test
below overrides that mock locally to drive the failure cases.
"""

from unittest.mock import patch

from httpx import AsyncClient

from app.services.storage_service import StorageObjectNotFound, StorageService
from tests.integration.conftest import advance_to


class TestDocumentConfirmVerification:
    async def test_confirm_rejects_missing_object_with_400(
        self, client: AsyncClient, admin_token: str
    ):
        """Client never PUT the object — verify_upload raises, route returns 400."""
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "draft", ref="DOC-MISSING")

        # Create a PO so we have a valid entity_id to attach a document to.
        r = await client.post(
            "/api/v1/purchase-orders",
            json={
                "po_number": "PO-DOC-MISSING",
                "po_date": "2026-01-10",
                "product_description": "Tiles",
                "quantity": "100",
                "quantity_unit": "boxes",
                "total_value": "10000.00",
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        po_id = r.json()["id"]
        r = await client.post(
            f"/api/v1/bookings/{sid}/purchase-orders",
            json={"purchase_order_id": po_id},
            headers=h,
        )
        assert r.status_code == 200, r.json()

        with patch.object(
            StorageService,
            "verify_upload",
            side_effect=StorageObjectNotFound("object not found in storage: k.pdf"),
        ):
            r = await client.post(
                "/api/v1/documents/confirm",
                params={"entity_type": "purchase_order", "entity_id": po_id},
                json={
                    "file_key": "k.pdf",
                    "file_name": "po.pdf",
                    "mime_type": "application/pdf",
                },
                headers=h,
            )

        assert r.status_code == 400, r.json()
        assert "not found" in r.json()["detail"].lower()

    async def test_confirm_rejects_oversize_object_with_413(
        self, client: AsyncClient, admin_token: str
    ):
        """R2 reports an object larger than MAX_FILE_SIZE_BYTES — return 413."""
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "draft", ref="DOC-OVERSIZE")

        r = await client.post(
            "/api/v1/purchase-orders",
            json={
                "po_number": "PO-DOC-OVERSIZE",
                "po_date": "2026-01-10",
                "product_description": "Tiles",
                "quantity": "100",
                "quantity_unit": "boxes",
                "total_value": "10000.00",
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        po_id = r.json()["id"]
        r = await client.post(
            f"/api/v1/bookings/{sid}/purchase-orders",
            json={"purchase_order_id": po_id},
            headers=h,
        )
        assert r.status_code == 200, r.json()

        oversize = StorageService.MAX_FILE_SIZE_BYTES + 1
        with patch.object(
            StorageService,
            "verify_upload",
            return_value={
                "size": oversize,
                "etag": "fake-etag",
                "content_type": "application/pdf",
            },
        ):
            r = await client.post(
                "/api/v1/documents/confirm",
                params={"entity_type": "purchase_order", "entity_id": po_id},
                json={
                    "file_key": "k.pdf",
                    "file_name": "po.pdf",
                    "mime_type": "application/pdf",
                },
                headers=h,
            )

        assert r.status_code == 413, r.json()
        assert "maximum size" in r.json()["detail"].lower()

    async def test_confirm_persists_real_size_from_r2(self, client: AsyncClient, admin_token: str):
        """Server uses the size R2 reports, not the client-claimed value."""
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await advance_to(client, h, "draft", ref="DOC-REAL-SIZE")

        r = await client.post(
            "/api/v1/purchase-orders",
            json={
                "po_number": "PO-DOC-REAL-SIZE",
                "po_date": "2026-01-10",
                "product_description": "Tiles",
                "quantity": "100",
                "quantity_unit": "boxes",
                "total_value": "10000.00",
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        po_id = r.json()["id"]
        r = await client.post(
            f"/api/v1/bookings/{sid}/purchase-orders",
            json={"purchase_order_id": po_id},
            headers=h,
        )
        assert r.status_code == 200, r.json()

        # Client lies about size; server should record what R2 actually has.
        # Autouse mock already returns size=1024 — override only to widen the gap.
        with patch.object(
            StorageService,
            "verify_upload",
            return_value={
                "size": 4242,
                "etag": "fake-etag",
                "content_type": "application/pdf",
            },
        ):
            r = await client.post(
                "/api/v1/documents/confirm",
                params={"entity_type": "purchase_order", "entity_id": po_id},
                json={
                    "file_key": "k.pdf",
                    "file_name": "po.pdf",
                    "mime_type": "application/pdf",
                    "file_size_bytes": 1,  # client-claimed, must be ignored
                },
                headers=h,
            )

        assert r.status_code == 200, r.json()
        assert r.json()["file_size_bytes"] == 4242
