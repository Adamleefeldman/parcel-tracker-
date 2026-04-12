from httpx import AsyncClient


class TestRolePermissions:
    async def test_admin_can_create_shipment(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/v1/shipments",
            json={"reference": "RBAC-SHIP-ADMIN"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    async def test_morocco_agent_cannot_create_shipment(
        self, client: AsyncClient, morocco_agent_token: str
    ):
        resp = await client.post(
            "/api/v1/shipments",
            json={"reference": "RBAC-SHIP-MA"},
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_uk_agent_cannot_create_shipment(self, client: AsyncClient, uk_agent_token: str):
        resp = await client.post(
            "/api/v1/shipments",
            json={"reference": "RBAC-SHIP-UK"},
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_customer_cannot_create_shipment(self, client: AsyncClient, customer_token: str):
        resp = await client.post(
            "/api/v1/shipments",
            json={"reference": "RBAC-SHIP-CUST"},
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert resp.status_code == 403

    async def test_morocco_agent_cannot_invite(self, client: AsyncClient, morocco_agent_token: str):
        resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "new@test.com", "role": "customer"},
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_uk_agent_cannot_invite(self, client: AsyncClient, uk_agent_token: str):
        resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "new2@test.com", "role": "customer"},
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_customer_cannot_invite(self, client: AsyncClient, customer_token: str):
        resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "new3@test.com", "role": "customer"},
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert resp.status_code == 403

    async def test_admin_can_list_shipments(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data and isinstance(data["items"], list)
        assert "total" in data

    async def test_morocco_agent_can_list_shipments(
        self, client: AsyncClient, morocco_agent_token: str
    ):
        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []  # no memberships yet — empty list, not 403

    async def test_uk_agent_can_list_shipments(self, client: AsyncClient, uk_agent_token: str):
        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_customer_can_list_shipments(self, client: AsyncClient, customer_token: str):
        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_morocco_agent_cannot_add_member(
        self, client: AsyncClient, morocco_agent_token: str, shipment: str
    ):
        resp = await client.post(
            f"/api/v1/shipments/{shipment}/members",
            json={"user_id": "00000000-0000-0000-0000-000000000001"},
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_uk_agent_cannot_add_member(
        self, client: AsyncClient, uk_agent_token: str, shipment: str
    ):
        resp = await client.post(
            f"/api/v1/shipments/{shipment}/members",
            json={"user_id": "00000000-0000-0000-0000-000000000001"},
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_customer_cannot_add_member(
        self, client: AsyncClient, customer_token: str, shipment: str
    ):
        resp = await client.post(
            f"/api/v1/shipments/{shipment}/members",
            json={"user_id": "00000000-0000-0000-0000-000000000001"},
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert resp.status_code == 403


class TestShipmentScopedAccess:
    async def test_non_member_sees_empty_list(
        self, client: AsyncClient, uk_agent_token: str, shipment: str
    ):
        """UK Agent exists but has no memberships — list must be empty."""
        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_member_sees_only_their_shipment(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str
    ):
        """UK Agent assigned to A sees A but not B in their list."""
        # Admin creates two shipments
        resp_a = await client.post(
            "/api/v1/shipments",
            json={"reference": "SCOPE-SHIP-A"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        ship_a_id = resp_a.json()["id"]

        await client.post(
            "/api/v1/shipments",
            json={"reference": "SCOPE-SHIP-B"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Fetch the UK Agent's user id from their token by hitting the invite flow
        from jose import jwt

        from app.core.config import get_settings

        uk_user_id = jwt.decode(
            uk_agent_token,
            get_settings().SECRET_KEY,
            algorithms=[get_settings().JWT_ALGORITHM],
        )["sub"]

        # Admin assigns UK Agent to Shipment A only
        await client.post(
            f"/api/v1/shipments/{ship_a_id}/members",
            json={"user_id": uk_user_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # UK Agent's list should contain A but not B
        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert resp.status_code == 200
        ids = [s["id"] for s in resp.json()["items"]]
        assert ship_a_id in ids
        assert len(ids) == 1  # B must not appear

    async def test_admin_sees_all_shipments(self, client: AsyncClient, admin_token: str):
        """Admin sees both shipments regardless of explicit membership."""
        await client.post(
            "/api/v1/shipments",
            json={"reference": "SCOPE-ADMIN-A"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        await client.post(
            "/api/v1/shipments",
            json={"reference": "SCOPE-ADMIN-B"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 2

    async def test_unassigned_agent_sees_nothing(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str, shipment: str
    ):
        """Morocco Agent with no memberships always gets an empty list."""
        resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# ── Shipment membership flow ──────────────────────────────────────────────────


class TestShipmentMembership:
    def _decode_user_id(self, token: str) -> str:
        """Extract user UUID from a JWT access token without making an API call."""
        from jose import jwt

        from app.core.config import get_settings

        settings = get_settings()
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])["sub"]

    async def test_assignment_activates_list_access(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str, shipment: str
    ):
        """Before assignment: empty list. After assignment: shipment appears."""
        # Phase 1 — UK Agent has no memberships
        before = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        assert before.json()["items"] == []

        # Admin assigns UK Agent to the shipment
        uk_user_id = self._decode_user_id(uk_agent_token)
        assign = await client.post(
            f"/api/v1/shipments/{shipment}/members",
            json={"user_id": uk_user_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert assign.status_code == 200

        # Phase 2 — Shipment now appears in UK Agent's list
        after = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {uk_agent_token}"},
        )
        ids = [s["id"] for s in after.json()["items"]]
        assert shipment in ids

    async def test_assigning_non_existent_user_rejected(
        self, client: AsyncClient, admin_token: str, shipment: str
    ):
        """Route now validates user existence — unknown user_id returns 404."""
        import uuid

        fake_user_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/v1/shipments/{shipment}/members",
            json={"user_id": fake_user_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "User not found"

    async def test_assigning_to_non_existent_shipment_rejected(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str
    ):
        """Route now validates shipment existence — unknown shipment_id returns 404."""
        import uuid

        fake_shipment_id = str(uuid.uuid4())
        uk_user_id = self._decode_user_id(uk_agent_token)
        resp = await client.post(
            f"/api/v1/shipments/{fake_shipment_id}/members",
            json={"user_id": uk_user_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Shipment not found"

    async def test_duplicate_membership_rejected(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str, shipment: str
    ):
        """Adding the same user twice now returns 409 instead of crashing with 500."""
        uk_user_id = self._decode_user_id(uk_agent_token)
        payload = {"user_id": uk_user_id}
        headers = {"Authorization": f"Bearer {admin_token}"}

        first = await client.post(
            f"/api/v1/shipments/{shipment}/members",
            json=payload,
            headers=headers,
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/v1/shipments/{shipment}/members",
            json=payload,
            headers=headers,
        )
        assert second.status_code == 409
        assert second.json()["detail"] == "User is already a member of this shipment"


# ── Admin bypass ──────────────────────────────────────────────────────────────


class TestAdminBypass:
    async def test_admin_accesses_shipment_without_membership(
        self, client: AsyncClient, admin_token: str, second_admin_token: str, shipment: str
    ):
        """
        Admin 1 creates the shipment (auto-added as member).
        Admin 2 has no row in shipment_users for this shipment.
        Admin 2 must still get 200 via the _AdminMembership bypass.
        """
        resp = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {second_admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == shipment

    async def test_non_member_non_admin_is_blocked(
        self, client: AsyncClient, morocco_agent_token: str, shipment: str
    ):
        """
        Morocco Agent has no membership for this shipment.
        Must receive 403 — proving the bypass is admin-only.
        """
        resp = await client.get(
            f"/api/v1/shipments/{shipment}",
            headers={"Authorization": f"Bearer {morocco_agent_token}"},
        )
        assert resp.status_code == 403

    async def test_admin_sees_all_shipments_in_list(
        self, client: AsyncClient, admin_token: str, second_admin_token: str
    ):
        """
        Admin 1 creates a shipment. Admin 2 never touched it.
        Admin 2's GET /shipments list must include it — the admin
        list query branch (role == ADMIN → no membership join) is exercised.
        """
        create_resp = await client.post(
            "/api/v1/shipments",
            json={"reference": "BYPASS-SHIP-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        ship_id = create_resp.json()["id"]

        list_resp = await client.get(
            "/api/v1/shipments",
            headers={"Authorization": f"Bearer {second_admin_token}"},
        )
        assert list_resp.status_code == 200
        ids = [s["id"] for s in list_resp.json()["items"]]
        assert ship_id in ids
