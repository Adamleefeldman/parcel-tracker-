"""
JWT token revocation tests.

Validates the P1 security feature where logout revokes both access and
refresh tokens via a Redis deny-list keyed on the JWT's ``jti`` claim.
"""

from httpx import AsyncClient
from jose import jwt as jose_jwt

from tests.integration.conftest import login_and_get_tokens, seed_admin


class TestTokenRevocation:
    """POST /auth/logout revokes tokens; revoked tokens are rejected globally."""

    async def test_access_token_contains_jti_claim(self, client: AsyncClient):
        """The jti claim is the foundation of revocation — verify it exists."""
        await seed_admin()
        tokens = await login_and_get_tokens(client, "admin@test.com", "adminpass123")

        claims = jose_jwt.get_unverified_claims(tokens["access_token"])
        assert "jti" in claims, "Access token must contain a 'jti' claim"
        assert isinstance(claims["jti"], str) and len(claims["jti"]) > 0

    async def test_logout_revokes_access_token(self, client: AsyncClient):
        """After logout, the same access token is rejected with 401."""
        await seed_admin()
        tokens = await login_and_get_tokens(client, "admin@test.com", "adminpass123")
        access = tokens["access_token"]
        refresh = tokens["refresh_token"]
        h = {"Authorization": f"Bearer {access}"}

        # Verify token works before logout
        r = await client.get("/api/v1/shipments", headers=h)
        assert r.status_code == 200

        # Logout
        r = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh},
            headers=h,
        )
        assert r.status_code == 200

        # Same access token should now be rejected
        r = await client.get("/api/v1/shipments", headers=h)
        assert r.status_code == 401
        assert "revoked" in r.json()["detail"].lower()

    async def test_logout_revokes_refresh_token(self, client: AsyncClient):
        """After logout, the refresh token cannot be used to obtain new tokens."""
        await seed_admin()
        tokens = await login_and_get_tokens(client, "admin@test.com", "adminpass123")
        h = {"Authorization": f"Bearer {tokens['access_token']}"}

        # Logout
        await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=h,
        )

        # Refresh with the old token should fail
        r = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert r.status_code == 401

    async def test_revoked_token_rejected_on_non_auth_routes(self, client: AsyncClient):
        """Revocation is enforced globally by get_current_user, not just auth routes."""
        await seed_admin()
        tokens = await login_and_get_tokens(client, "admin@test.com", "adminpass123")
        access = tokens["access_token"]
        h = {"Authorization": f"Bearer {access}"}

        # Create a shipment while token is valid
        r = await client.post(
            "/api/v1/shipments",
            json={"reference": "REVOKE-TEST"},
            headers=h,
        )
        assert r.status_code == 200
        sid = r.json()["id"]

        # Logout to revoke
        await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=h,
        )

        # Try accessing the shipment — should be rejected
        r = await client.get(f"/api/v1/shipments/{sid}", headers=h)
        assert r.status_code == 401
