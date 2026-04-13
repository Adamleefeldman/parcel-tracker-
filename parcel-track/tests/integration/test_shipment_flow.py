"""
Integration test skeleton.
Run with: pytest tests/ -v

Uses an in-memory SQLite database for speed.
Replace DATABASE_URL with a real test Postgres instance for full type compatibility.
Fixtures (client, admin_token, setup_db) are provided by conftest.py.
"""

from httpx import AsyncClient

# ── Auth tests ────────────────────────────────────────────────────────────────


class TestAuth:
    async def test_login_wrong_password(self, client: AsyncClient, admin_token):
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@test.com",
                "password": "wrongpassword",
            },
        )
        assert resp.status_code == 401

    async def test_protected_route_without_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/shipments")
        assert resp.status_code == 401

    async def test_invite_and_accept(self, client: AsyncClient, admin_token):
        # Admin creates invite for Morocco agent
        resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "agent@morocco.com", "role": "morocco_agent"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        token = resp.json()["invite_token"]

        # Agent accepts invite
        resp = await client.post(
            "/api/v1/auth/accept-invite",
            json={
                "token": token,
                "name": "Morocco Agent",
                "password": "agentpass123",
            },
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()


# ── Shipment lifecycle tests ───────────────────────────────────────────────────


class TestShipmentLifecycle:
    async def test_create_shipment(self, client: AsyncClient, admin_token):
        resp = await client.post(
            "/api/v1/shipments",
            json={"reference": "SHIP-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["reference"] == "SHIP-001"
        assert resp.json()["status"] == "draft"

    async def test_duplicate_reference_rejected(self, client: AsyncClient, admin_token):
        await client.post(
            "/api/v1/shipments",
            json={"reference": "SHIP-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = await client.post(
            "/api/v1/shipments",
            json={"reference": "SHIP-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    async def test_cannot_skip_state(self, client: AsyncClient, admin_token):
        """Cannot jump from draft to BL_ISSUED — must follow the chain."""
        # This would require mocking the full state but the logic is in ShipmentService
        # Left as a placeholder for full integration testing
        pass

    async def test_non_admin_cannot_create_shipment(self, client: AsyncClient, admin_token):
        """Morocco agent should not be able to create a shipment."""
        # Create Morocco agent
        invite_resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "ma@test.com", "role": "morocco_agent"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        token = invite_resp.json()["invite_token"]
        accept_resp = await client.post(
            "/api/v1/auth/accept-invite",
            json={
                "token": token,
                "name": "MA",
                "password": "agentpass123",
            },
        )
        agent_token = accept_resp.json()["access_token"]

        resp = await client.post(
            "/api/v1/shipments",
            json={"reference": "SHIP-002"},
            headers={"Authorization": f"Bearer {agent_token}"},
        )
        assert resp.status_code == 403
