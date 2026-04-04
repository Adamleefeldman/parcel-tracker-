"""
Day 4 integration tests: Shipment CRUD

Covers:
  - GET /shipments with status and date filters
  - GET /shipments/{id} response shape (ShipmentDetailOut)
  - PATCH /shipments/{id} — partial update

Fixtures (client, admin_token, shipment, role tokens, setup_db) are
provided by conftest.py. pytest-asyncio auto mode means no decorator needed.
"""
import uuid
from httpx import AsyncClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_user_id(token: str) -> str:
    """Extract user UUID from a JWT without an API call."""
    from jose import jwt
    from app.core.config import get_settings
    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])["sub"]


async def _create_shipment(client: AsyncClient, admin_token: str, reference: str) -> str:
    """Create a shipment and return its id."""
    resp = await client.post(
        "/api/v1/shipments",
        json={"reference": reference},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Shipment creation failed: {resp.json()}"
    return resp.json()["id"]


async def _assign_member(client: AsyncClient, admin_token: str, shipment_id: str, user_token: str):
    """Add a user (identified by their token) to a shipment."""
    user_id = _decode_user_id(user_token)
    resp = await client.post(
        f"/api/v1/shipments/{shipment_id}/members",
        json={"user_id": user_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Member assignment failed: {resp.json()}"


# ── GET /shipments filters ─────────────────────────────────────────────────────

class TestShipmentListFilters:
    """
    Exercises the status and date_from / date_to query parameters added in Task 2.
    All tests use the admin token so the membership join is bypassed — we're
    testing filter logic only, not access control (that lives in test_rbac.py).
    """

    async def test_filter_by_status_returns_matching(
        self, client: AsyncClient, admin_token: str
    ):
        """
        Creates one shipment (status=draft). Filter by status=draft must return it.
        Filter by status=in_transit must return nothing.
        """
        await _create_shipment(client, admin_token, "FILTER-STATUS-001")

        draft_resp = await client.get(
            "/api/v1/shipments?status=draft",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert draft_resp.status_code == 200
        statuses = [s["status"] for s in draft_resp.json()]
        assert all(s == "draft" for s in statuses)
        assert len(statuses) >= 1

    async def test_filter_by_status_no_match_returns_empty(
        self, client: AsyncClient, admin_token: str
    ):
        """No shipment has status=in_transit — result must be an empty list, not an error."""
        await _create_shipment(client, admin_token, "FILTER-STATUS-002")

        resp = await client.get(
            "/api/v1/shipments?status=in_transit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_filter_by_invalid_status_returns_422(
        self, client: AsyncClient, admin_token: str
    ):
        """
        FastAPI validates enum query params automatically.
        An unrecognised status value must produce a 422 Unprocessable Entity,
        not a 500 or silent empty list.
        """
        resp = await client.get(
            "/api/v1/shipments?status=nonexistent_status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    async def test_filter_date_from_excludes_earlier(
        self, client: AsyncClient, admin_token: str
    ):
        """
        date_from=2099-01-01 is in the future — no shipment created now
        should match, so the result must be empty.
        """
        await _create_shipment(client, admin_token, "FILTER-DATE-001")

        resp = await client.get(
            "/api/v1/shipments?date_from=2099-01-01",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_filter_date_to_includes_today(
        self, client: AsyncClient, admin_token: str
    ):
        """
        date_to=2099-12-31 is far in the future — a shipment created now
        must appear in results.
        """
        ship_id = await _create_shipment(client, admin_token, "FILTER-DATE-002")

        resp = await client.get(
            "/api/v1/shipments?date_to=2099-12-31",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        ids = [s["id"] for s in resp.json()]
        assert ship_id in ids

    async def test_status_and_date_filters_combine(
        self, client: AsyncClient, admin_token: str
    ):
        """
        Both filters active simultaneously. A shipment that matches status=draft
        but is excluded by date_from should not appear.
        """
        await _create_shipment(client, admin_token, "FILTER-COMBO-001")

        # date_from far in future: should exclude all current shipments even though status matches
        resp = await client.get(
            "/api/v1/shipments?status=draft&date_from=2099-01-01",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_no_filters_returns_all(
        self, client: AsyncClient, admin_token: str
    ):
        """Baseline: no query params returns all shipments for an admin."""
        id_a = await _create_shipment(client, admin_token, "FILTER-NONE-A")
        id_b = await _create_shipment(client, admin_token, "FILTER-NONE-B")

        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        ids = [s["id"] for s in resp.json()]
        assert id_a in ids
        assert id_b in ids

    async def test_non_member_filtered_list_still_scoped(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str
    ):
        """
        UK Agent is a member of shipment A but not B.
        Even with no status filter, the list must only return A — not B.
        Confirming the membership scope survives the query-builder refactor.
        """
        ship_a = await _create_shipment(client, admin_token, "FILTER-SCOPE-A")
        await _create_shipment(client, admin_token, "FILTER-SCOPE-B")
        await _assign_member(client, admin_token, ship_a, uk_agent_token)

        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert resp.status_code == 200
        ids = [s["id"] for s in resp.json()]
        assert ship_a in ids
        assert len(ids) == 1


# ── GET /shipments/{id} response shape ────────────────────────────────────────

class TestShipmentDetail:
    """
    Verifies that GET /shipments/{id} now returns the ShipmentDetailOut shape,
    including all nested relationship keys, even when those relationships are
    empty/None (because the shipment was just created).
    """

    async def test_detail_contains_base_fields(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        """id, reference, status, created_at, updated_at must always be present."""
        resp = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        for field in ("id", "reference", "status", "created_at", "updated_at"):
            assert field in body, f"Missing field: {field}"

    async def test_detail_contains_nested_relationship_keys(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        """
        All nested relationship fields declared in ShipmentDetailOut must be
        present in the response (even if null/empty — they must exist as keys).
        A missing key means the selectinload or schema field is broken.
        """
        resp = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()

        # These keys must exist — value may be null or [] for a fresh shipment
        assert "purchase_order" in body
        assert "invoice" in body
        assert "payments" in body
        assert "bill_of_lading" in body
        assert "clearing_docs" in body
        assert "delivery_points" in body

    async def test_detail_fresh_shipment_relationships_are_empty(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        """
        A freshly created shipment has no linked records yet.
        Optional fields must be null; list fields must be empty lists.
        """
        resp = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        body = resp.json()
        assert body["purchase_order"] is None
        assert body["invoice"] is None
        assert body["payments"] == []
        assert body["bill_of_lading"] is None
        assert body["clearing_docs"] is None
        assert body["delivery_points"] == []

    async def test_detail_unauthorised_non_member_returns_403(
        self, client: AsyncClient, morocco_agent_token: str, shipment: str
    ):
        """
        Morocco Agent has not been added to this shipment — must get 403.
        Confirming require_shipment_member still guards the detail route.
        """
        resp = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_detail_member_can_access(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str, shipment: str
    ):
        """
        UK Agent assigned to the shipment must get 200 on the detail endpoint.
        """
        await _assign_member(client, admin_token, shipment, uk_agent_token)

        resp = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == shipment

    async def test_detail_unknown_id_returns_404(
        self, client: AsyncClient, admin_token: str
    ):
        """A well-formed UUID that doesn't exist in the DB must return 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/v1/shipments/{fake_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


# ── PATCH /shipments/{id} ─────────────────────────────────────────────────────

class TestShipmentPatch:
    """
    Covers the PATCH endpoint implemented in Task 1.
    """

    async def test_admin_can_update_reference(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        """Admin PATCH with a new reference — response must reflect the change."""
        resp = await client.patch(
            f"/api/v1/shipments/{shipment}",
            json={"reference": "UPDATED-REF-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["reference"] == "UPDATED-REF-001"

    async def test_patch_persists_across_get(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        """
        After a successful PATCH, a subsequent GET must return the updated value.
        This confirms the flush/commit path wrote to the DB, not just the
        in-memory ORM object.
        """
        await client.patch(
            f"/api/v1/shipments/{shipment}",
            json={"reference": "PERSIST-CHECK-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        get_resp = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert get_resp.json()["reference"] == "PERSIST-CHECK-001"

    async def test_patch_empty_body_is_no_op(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        """
        PATCH with an empty body must succeed (200) and leave the shipment unchanged.
        This validates exclude_unset=True — no fields are overwritten with None.
        """
        original = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        original_reference = original.json()["reference"]

        resp = await client.patch(
            f"/api/v1/shipments/{shipment}",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["reference"] == original_reference

    async def test_non_admin_cannot_patch(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str, shipment: str
    ):
        """Morocco Agent must receive 403 even if they are a member of the shipment."""
        await _assign_member(client, admin_token, shipment, morocco_agent_token)

        resp = await client.patch(
            f"/api/v1/shipments/{shipment}",
            json={"reference": "SHOULD-FAIL"},
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_patch_nonexistent_shipment_returns_404(
        self, client: AsyncClient, admin_token: str
    ):
        """A well-formed UUID that doesn't exist must return 404, not 500."""
        fake_id = str(uuid.uuid4())
        resp = await client.patch(
            f"/api/v1/shipments/{fake_id}",
            json={"reference": "GHOST"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    async def test_patch_to_duplicate_reference_returns_error(
        self, client: AsyncClient, admin_token: str
    ):
        """
        If two shipments exist and we try to rename one to the other's reference,
        the DB unique constraint must fire and the API must return an error (not 200).
        """
        ship_a = await _create_shipment(client, admin_token, "PATCH-DUP-A")
        await _create_shipment(client, admin_token, "PATCH-DUP-B")

        resp = await client.patch(
            f"/api/v1/shipments/{ship_a}",
            json={"reference": "PATCH-DUP-B"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Unique constraint violation — must not be 200
        assert resp.status_code != 200
