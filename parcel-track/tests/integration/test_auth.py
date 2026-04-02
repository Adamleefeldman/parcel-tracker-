from httpx import AsyncClient


class TestInvite:

    async def test_invite_returns_token(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "newuser@test.com", "role": "uk_agent"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "invite_token" in body
        assert body["email"] == "newuser@test.com"
        assert "expires_at" in body

    async def test_invite_token_is_usable(self, client: AsyncClient, admin_token: str):
        invite_resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "agent@test.com", "role": "uk_agent"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        token = invite_resp.json()["invite_token"]

        resp = await client.post("/api/v1/auth/accept-invite", json={
            "token": token, "name": "UK Agent", "password": "pass123456",
        })
        assert resp.status_code == 200

    async def test_non_admin_cannot_invite(self, client: AsyncClient, admin_token: str):
        # Create a non-admin user via the invite flow
        invite_resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "agent@test.com", "role": "morocco_agent"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        token = invite_resp.json()["invite_token"]
        accept_resp = await client.post("/api/v1/auth/accept-invite", json={
            "token": token, "name": "MA", "password": "pass123456",
        })
        agent_token = accept_resp.json()["access_token"]

        # Non-admin attempts to create an invite
        resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "another@test.com", "role": "customer"},
            headers={"Authorization": f"Bearer {agent_token}"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_invite(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "x@test.com", "role": "customer"},
        )
        assert resp.status_code == 401


class TestAcceptInvite:

    async def test_accept_invite_creates_user_and_returns_tokens(self, client: AsyncClient, admin_token: str):
        invite_resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "new@test.com", "role": "customer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        token = invite_resp.json()["invite_token"]

        resp = await client.post("/api/v1/auth/accept-invite", json={
            "token": token, "name": "New User", "password": "pass123456",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_invite_token_single_use(self, client: AsyncClient, admin_token: str):
        invite_resp = await client.post(
            "/api/v1/auth/invite",
            json={"email": "once@test.com", "role": "customer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        token = invite_resp.json()["invite_token"]

        await client.post("/api/v1/auth/accept-invite", json={
            "token": token, "name": "User", "password": "pass123456",
        })
        # Second use of the same token must be rejected
        resp = await client.post("/api/v1/auth/accept-invite", json={
            "token": token, "name": "User", "password": "pass123456",
        })
        assert resp.status_code == 400

    async def test_invalid_invite_token_rejected(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/accept-invite", json={
            "token": "totallyinvalidtoken", "name": "User", "password": "pass123456",
        })
        assert resp.status_code == 400


class TestLogin:

    async def test_login_returns_both_tokens(self, client: AsyncClient, admin_token: str):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "admin@test.com", "password": "adminpass123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, admin_token: str):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "admin@test.com", "password": "wrongpassword",
        })
        assert resp.status_code == 401

    async def test_login_unknown_email(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nobody@test.com", "password": "pass123456",
        })
        assert resp.status_code == 401


class TestRefresh:

    async def test_refresh_returns_new_access_token(self, client: AsyncClient, admin_refresh_token: str):
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": admin_refresh_token,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_refresh_rotates_token(self, client: AsyncClient, admin_refresh_token: str):
        # Use the token once
        await client.post("/api/v1/auth/refresh", json={"refresh_token": admin_refresh_token})
        # Old token must now be rejected
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": admin_refresh_token})
        assert resp.status_code == 401

    async def test_invalid_refresh_token_rejected(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "notarealtoken"})
        assert resp.status_code == 401

    async def test_revoked_refresh_token_rejected(self, client: AsyncClient, admin_token: str):
        from sqlalchemy import select
        from app.db.models import RefreshToken
        from app.core.security import hash_token
        from tests.integration.conftest import TestSession

        # Get a fresh refresh token via login
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": "admin@test.com", "password": "adminpass123",
        })
        refresh_tok = login_resp.json()["refresh_token"]

        # Revoke it directly in the DB
        async with TestSession() as db:
            result = await db.execute(
                select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_tok))
            )
            record = result.scalar_one()
            record.revoked = True
            await db.commit()

        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_tok})
        assert resp.status_code == 401
