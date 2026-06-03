"""Integration tests for the admin People/System read endpoints (mobile Phase 13b).

Three admin-only, read-only list endpoints:
  * GET /api/v1/users        — users with optional role / is_active filters.
  * GET /api/v1/invites      — invites filtered by status; token_hash NEVER leaks.
  * GET /api/v1/audit-logs   — global audit feed, newest first, actor_name joined.

Each test runs against a fresh DB (`setup_db` drops/creates per test), so only
the rows a test seeds (plus fixture-seeded admins) exist.
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.core.enums import UserRole
from app.core.security import create_invite_token, hash_password
from app.db.models import AuditLog, InviteToken, User
from tests.integration.conftest import TestSession

USERS_URL = "/api/v1/users"
INVITES_URL = "/api/v1/invites"
AUDIT_URL = "/api/v1/audit-logs"


# ── Seed helpers ──────────────────────────────────────────────────────────────


async def _admin_id() -> uuid.UUID:
    async with TestSession() as db:
        return (
            await db.execute(select(User.id).where(User.email == "admin@test.com"))
        ).scalar_one()


async def _seed_user(email: str, role: UserRole, *, is_active: bool = True) -> uuid.UUID:
    async with TestSession() as db:
        user = User(
            email=email,
            hashed_password=hash_password("testpass123"),
            name=email.split("@")[0].title(),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        await db.commit()
        return user.id


async def _seed_invite(
    email: str,
    role: UserRole,
    *,
    used: bool = False,
    expires_in_days: int = 7,
) -> str:
    """Insert an invite directly. Returns the stored token_hash so tests can
    assert it never appears in any response body."""
    _raw, token_hash = create_invite_token()
    created_by = await _admin_id()
    async with TestSession() as db:
        invite = InviteToken(
            token_hash=token_hash,
            email=email,
            role=role,
            created_by=created_by,
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
            used=used,
        )
        db.add(invite)
        await db.commit()
    return token_hash


async def _seed_audit_log(
    *,
    action: str,
    actor_id: uuid.UUID,
    booking_id: uuid.UUID | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    async with TestSession() as db:
        log = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type="booking",
            entity_id=uuid.uuid4(),
            booking_id=booking_id,
            old_value=old_value,
            new_value=new_value,
        )
        if created_at is not None:
            log.created_at = created_at
        db.add(log)
        await db.commit()
        return log.id


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Users ─────────────────────────────────────────────────────────────────────


async def test_list_users_shape_and_no_secret_leak(client: AsyncClient, admin_token: str):
    await _seed_user("ukagent@x.com", UserRole.UK_AGENT)

    resp = await client.get(USERS_URL, headers=_h(admin_token))
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert set(body) == {"items", "total", "offset", "limit"}
    assert body["total"] >= 2  # admin fixture + seeded agent

    item = body["items"][0]
    assert set(item) == {"id", "email", "name", "role", "is_active", "created_at"}
    # No secret / sensitive fields ever serialised.
    for leaked in ("hashed_password", "expo_push_token", "token_hash", "password"):
        assert leaked not in item


async def test_list_users_role_and_active_filters(client: AsyncClient, admin_token: str):
    await _seed_user("morocco@x.com", UserRole.MOROCCO_AGENT)
    await _seed_user("cust@x.com", UserRole.CUSTOMER)
    await _seed_user("inactive@x.com", UserRole.CUSTOMER, is_active=False)

    # role filter
    resp = await client.get(USERS_URL, params={"role": "customer"}, headers=_h(admin_token))
    assert resp.status_code == 200
    assert {u["role"] for u in resp.json()["items"]} == {"customer"}

    # is_active filter
    resp = await client.get(USERS_URL, params={"is_active": False}, headers=_h(admin_token))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items and all(u["is_active"] is False for u in items)


async def test_list_users_pagination(client: AsyncClient, admin_token: str):
    for i in range(5):
        await _seed_user(f"u{i}@x.com", UserRole.CUSTOMER)

    resp = await client.get(USERS_URL, params={"limit": 2, "offset": 0}, headers=_h(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["total"] >= 6  # 5 customers + admin


# ── Invites ─────────────────────────────────────────────────────────────────────


async def test_list_invites_default_pending_excludes_used_and_expired(
    client: AsyncClient, admin_token: str
):
    await _seed_invite("pending@x.com", UserRole.CUSTOMER)
    await _seed_invite("used@x.com", UserRole.CUSTOMER, used=True)
    await _seed_invite("expired@x.com", UserRole.CUSTOMER, expires_in_days=-1)

    resp = await client.get(INVITES_URL, headers=_h(admin_token))
    assert resp.status_code == 200, resp.json()
    emails = {i["email"] for i in resp.json()["items"]}
    assert emails == {"pending@x.com"}


async def test_list_invites_status_all_includes_everything(client: AsyncClient, admin_token: str):
    await _seed_invite("pending@x.com", UserRole.CUSTOMER)
    await _seed_invite("used@x.com", UserRole.CUSTOMER, used=True)
    await _seed_invite("expired@x.com", UserRole.CUSTOMER, expires_in_days=-1)

    resp = await client.get(INVITES_URL, params={"status": "all"}, headers=_h(admin_token))
    assert resp.status_code == 200
    emails = {i["email"] for i in resp.json()["items"]}
    assert emails == {"pending@x.com", "used@x.com", "expired@x.com"}


async def test_list_invites_status_expired_and_used_filters(client: AsyncClient, admin_token: str):
    await _seed_invite("pending@x.com", UserRole.CUSTOMER)
    await _seed_invite("used@x.com", UserRole.CUSTOMER, used=True)
    await _seed_invite("expired@x.com", UserRole.CUSTOMER, expires_in_days=-1)

    expired = await client.get(INVITES_URL, params={"status": "expired"}, headers=_h(admin_token))
    assert {i["email"] for i in expired.json()["items"]} == {"expired@x.com"}

    used = await client.get(INVITES_URL, params={"status": "used"}, headers=_h(admin_token))
    assert {i["email"] for i in used.json()["items"]} == {"used@x.com"}


async def test_list_invites_expired_flag_and_shape(client: AsyncClient, admin_token: str):
    await _seed_invite("pending@x.com", UserRole.CUSTOMER)
    await _seed_invite("expired@x.com", UserRole.CUSTOMER, expires_in_days=-1)

    resp = await client.get(INVITES_URL, params={"status": "all"}, headers=_h(admin_token))
    assert resp.status_code == 200
    by_email = {i["email"]: i for i in resp.json()["items"]}

    assert set(by_email["pending@x.com"]) == {
        "id",
        "email",
        "role",
        "expires_at",
        "created_at",
        "used",
        "expired",
    }
    assert by_email["pending@x.com"]["expired"] is False
    assert by_email["expired@x.com"]["expired"] is True


async def test_list_invites_never_serializes_token_hash(client: AsyncClient, admin_token: str):
    secret_hash = await _seed_invite("pending@x.com", UserRole.CUSTOMER)

    resp = await client.get(INVITES_URL, params={"status": "all"}, headers=_h(admin_token))
    assert resp.status_code == 200
    # Neither the field name nor the value may appear anywhere in the payload.
    assert "token_hash" not in resp.text
    assert secret_hash not in resp.text
    for item in resp.json()["items"]:
        assert "token_hash" not in item
        assert "token" not in item


# ── Audit logs ────────────────────────────────────────────────────────────────


async def test_list_audit_logs_newest_first_and_actor_name(client: AsyncClient, admin_token: str):
    admin_id = await _admin_id()
    base = datetime.now(UTC)
    await _seed_audit_log(action="booking.created", actor_id=admin_id, created_at=base)
    await _seed_audit_log(
        action="booking.status_changed",
        actor_id=admin_id,
        created_at=base + timedelta(minutes=5),
    )

    resp = await client.get(AUDIT_URL, headers=_h(admin_token))
    assert resp.status_code == 200, resp.json()
    items = resp.json()["items"]
    assert [i["action"] for i in items][:2] == ["booking.status_changed", "booking.created"]
    # actor_name joined from User (no lazy load).
    assert items[0]["actor_name"] == "Test Admin"
    assert set(items[0]) == {
        "id",
        "created_at",
        "actor_id",
        "actor_name",
        "action",
        "entity_type",
        "entity_id",
        "old_value",
        "new_value",
        "ip_address",
        "booking_id",
    }


async def test_list_audit_logs_passes_through_old_new_values(client: AsyncClient, admin_token: str):
    admin_id = await _admin_id()
    await _seed_audit_log(
        action="booking.status_changed",
        actor_id=admin_id,
        old_value='{"status": "DRAFT"}',
        new_value='{"status": "PO_SUBMITTED"}',
    )

    resp = await client.get(AUDIT_URL, headers=_h(admin_token))
    assert resp.status_code == 200
    log = resp.json()["items"][0]
    # Stored JSON strings passed through verbatim (not re-parsed server-side).
    assert log["old_value"] == '{"status": "DRAFT"}'
    assert log["new_value"] == '{"status": "PO_SUBMITTED"}'


async def test_list_audit_logs_actor_filter(client: AsyncClient, admin_token: str):
    admin_id = await _admin_id()
    other_id = await _seed_user("other@x.com", UserRole.UK_AGENT)
    await _seed_audit_log(action="a.one", actor_id=admin_id)
    await _seed_audit_log(action="a.two", actor_id=other_id)

    resp = await client.get(AUDIT_URL, params={"actor_id": str(other_id)}, headers=_h(admin_token))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items and all(i["actor_id"] == str(other_id) for i in items)
    assert {i["actor_name"] for i in items} == {"Other"}


async def test_list_audit_logs_booking_filter_and_pagination(client: AsyncClient, admin_token: str):
    admin_id = await _admin_id()
    booking_id = uuid.uuid4()
    # booking_id is a nullable FK to bookings — but seeded entries below use a
    # real booking row to satisfy the constraint.
    from app.db.models import Booking

    async with TestSession() as db:
        db.add(Booking(id=booking_id, reference="AUDIT-BK", created_by=admin_id))
        await db.commit()

    for i in range(3):
        await _seed_audit_log(action=f"x.{i}", actor_id=admin_id, booking_id=booking_id)
    await _seed_audit_log(action="other", actor_id=admin_id)  # different (null) booking

    resp = await client.get(
        AUDIT_URL,
        params={"booking_id": str(booking_id), "limit": 2},
        headers=_h(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert all(i["booking_id"] == str(booking_id) for i in body["items"])


# ── Auth / RBAC ─────────────────────────────────────────────────────────────────


async def test_endpoints_require_admin_role(
    client: AsyncClient,
    morocco_agent_token: str,
    uk_agent_token: str,
    customer_token: str,
):
    for url in (USERS_URL, INVITES_URL, AUDIT_URL):
        for token in (morocco_agent_token, uk_agent_token, customer_token):
            resp = await client.get(url, headers=_h(token))
            assert resp.status_code == 403, f"{url} expected 403, got {resp.status_code}"


async def test_endpoints_reject_anonymous(client: AsyncClient):
    for url in (USERS_URL, INVITES_URL, AUDIT_URL):
        resp = await client.get(url)
        assert resp.status_code == 401, f"{url} expected 401, got {resp.status_code}"


async def test_endpoints_allow_admin(client: AsyncClient, admin_token: str):
    for url in (USERS_URL, INVITES_URL, AUDIT_URL):
        resp = await client.get(url, headers=_h(admin_token))
        assert resp.status_code == 200, f"{url}: {resp.json()}"
