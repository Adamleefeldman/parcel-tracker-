import os

# Set APP_ENV before any app imports so rate limiting is disabled for tests.
os.environ.setdefault("APP_ENV", "testing")

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.core.enums import UserRole
from app.db.database import Base, get_db
from app.main import app

# Use real Postgres in CI (TEST_DATABASE_URL set by the workflow).
# Fall back to in-memory SQLite for fast local iteration.
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Pool strategy differs by backend:
#   Postgres  → NullPool: prevents asyncpg reusing connections across event loops
#               ("Future attached to a different loop" errors with per-test loops).
#   SQLite    → StaticPool: forces a single shared connection so every session
#               sees the same in-memory database. NullPool would give each new
#               connection a fresh empty DB, making setup_db's create_all invisible
#               to fixtures that open their own sessions.
_is_sqlite = TEST_DB_URL.startswith("sqlite")
engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    poolclass=StaticPool if _is_sqlite else NullPool,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


# ── Redis client reset ────────────────────────────────────────────────────────
# The Redis async client is a module-level singleton. pytest-asyncio creates a
# fresh event loop per test, so the cached client from a previous test is bound
# to a closed loop — causing "RuntimeError: Event loop is closed". Resetting
# the singleton before each test forces a new connection on the current loop.


@pytest_asyncio.fixture(autouse=True)
async def reset_redis():
    from app.core import redis as redis_module

    redis_module._redis_client = None
    yield
    if redis_module._redis_client is not None:
        await redis_module._redis_client.aclose()
        redis_module._redis_client = None


# ── Infrastructure mocks ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_storage_service():
    """
    Prevent every test from reaching AWS S3.

    StorageService has four methods that talk to the network:
      - generate_file_key  → builds an S3 object key string
      - get_upload_url     → calls boto3 to generate a pre-signed PUT URL
      - get_download_url   → calls boto3 to generate a pre-signed GET URL
      - verify_upload      → HEADs the bucket to confirm a presigned PUT landed

    Tests that exercise document-related flows (e.g. submit_po) need a
    Document row to exist in the DB.  That row is created via the
    POST /documents/confirm endpoint, which calls verify_upload (must succeed)
    and get_download_url (must return a URL).  Without this mock both calls
    crash immediately because there are no AWS credentials in the test
    environment.

    Using autouse=True means every test in this suite is protected
    automatically — no individual test needs to remember to opt in.
    """
    with (
        patch(
            "app.services.storage_service.StorageService.generate_file_key",
            return_value="test/uploads/fake-key.pdf",
        ),
        patch(
            "app.services.storage_service.StorageService.get_upload_url",
            return_value="https://fake-s3.example.com/upload",
        ),
        patch(
            "app.services.storage_service.StorageService.get_download_url",
            return_value="https://fake-s3.example.com/download",
        ),
        patch(
            "app.services.storage_service.StorageService.verify_upload",
            return_value={
                "size": 1024,
                "etag": "fake-etag",
                "content_type": "application/pdf",
            },
        ),
    ):
        yield


# ── Celery push-notification dispatch ────────────────────────────────────────
# NotificationService.send enqueues `send_push_notification.delay(notif_id)`.
# Under the integration test suite we have no Celery broker, no Expo credentials,
# and no interest in making outbound HTTP calls — so we replace `.delay` with a
# no-op. Tests that need to assert push behaviour can override this fixture
# locally with a stub that records the calls instead.


@pytest.fixture(autouse=True)
def mock_push_task():
    from app.background import tasks as bg_tasks

    with patch.object(bg_tasks.send_push_notification, "delay", lambda *a, **kw: None):
        yield


# ── Shared helper functions ───────────────────────────────────────────────────


async def seed_admin(email: str = "admin@test.com", password: str = "adminpass123") -> None:
    """Insert an admin user directly into the DB without logging in."""
    from app.core.security import hash_password
    from app.db.models import User

    async with TestSession() as db:
        db.add(
            User(
                email=email,
                hashed_password=hash_password(password),
                name="Test Admin",
                role=UserRole.ADMIN,
            )
        )
        await db.commit()


async def login_and_get_tokens(client: AsyncClient, email: str, password: str) -> dict:
    """Login and return the full token response dict (access_token, token_type, refresh_token)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()


def token_to_user_id(token: str) -> str:
    """
    Extract the user UUID from a JWT access token without re-hitting the DB.

    JWTs are base64url-encoded and publicly readable — the signature
    guarantees authenticity but the payload itself is not encrypted.
    get_unverified_claims() decodes the payload section only, skipping
    signature verification entirely.  This is safe for test helpers
    because we already know these tokens came from our own test fixtures.

    The 'sub' (subject) claim is set to the user's UUID string by
    create_access_token() in app/core/security.py.
    """
    claims = jose_jwt.get_unverified_claims(token)
    return claims["sub"]


async def _add_member(
    client: AsyncClient,
    admin_token: str,
    shipment_id: str,
    user_token: str,
    role_override: str | None = None,
) -> None:
    """
    Add a user as a member of a shipment via the admin API.

    This is a plain async helper (not a fixture) because it must be
    called mid-test with specific shipment IDs and user tokens that are
    only known at runtime.  The user's UUID is extracted from their JWT
    rather than making an extra /me round-trip.

    Role enforcement tests rely on this: a user must be a shipment member
    before the role check fires.  Without membership the request is
    rejected at the membership gate, masking whether the role gate works.
    """
    user_id = token_to_user_id(user_token)
    payload: dict = {"user_id": user_id}
    if role_override:
        payload["role_override"] = role_override

    resp = await client.post(
        f"/api/v1/shipments/{shipment_id}/members",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"_add_member failed: {resp.json()}"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    """Seed an admin user directly and return their access token."""
    async with TestSession() as db:
        from app.core.security import hash_password
        from app.db.models import User

        admin = User(
            email="admin@test.com",
            hashed_password=hash_password("adminpass123"),
            name="Test Admin",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@test.com",
            "password": "adminpass123",
        },
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def admin_refresh_token(client: AsyncClient):
    """Seed a second admin user and return their refresh token."""
    async with TestSession() as db:
        from app.core.security import hash_password
        from app.db.models import User

        admin = User(
            email="admin2@test.com",
            hashed_password=hash_password("adminpass123"),
            name="Test Admin 2",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin2@test.com",
            "password": "adminpass123",
        },
    )
    assert resp.status_code == 200
    return resp.json()["refresh_token"]


@pytest_asyncio.fixture
async def second_admin_token(client: AsyncClient):
    """Seed a second admin user directly — used to test admin bypass (no shipment membership)."""
    async with TestSession() as db:
        from app.core.security import hash_password
        from app.db.models import User

        admin = User(
            email="admin3@test.com",
            hashed_password=hash_password("adminpass123"),
            name="Test Admin 3",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin3@test.com",
            "password": "adminpass123",
        },
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _invite_and_register(
    client: AsyncClient, admin_token: str, email: str, role: str, name: str
) -> str:
    """Helper: admin sends invite, user accepts, returns the new user's access token."""
    invite_resp = await client.post(
        "/api/v1/auth/invite",
        json={"email": email, "role": role},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert invite_resp.status_code == 200, f"Invite failed: {invite_resp.json()}"
    token = invite_resp.json()["invite_token"]

    accept_resp = await client.post(
        "/api/v1/auth/accept-invite",
        json={
            "token": token,
            "name": name,
            "password": "testpass123",
        },
    )
    assert accept_resp.status_code == 200, f"Accept invite failed: {accept_resp.json()}"
    return accept_resp.json()["access_token"]


@pytest_asyncio.fixture
async def morocco_agent_token(client: AsyncClient, admin_token: str) -> str:
    """Create a Morocco Agent user via the invite flow and return their access token."""
    return await _invite_and_register(
        client,
        admin_token,
        email="morocco@test.com",
        role="morocco_agent",
        name="Morocco Agent",
    )


@pytest_asyncio.fixture
async def uk_agent_token(client: AsyncClient, admin_token: str) -> str:
    """Create a UK Agent user via the invite flow and return their access token."""
    return await _invite_and_register(
        client,
        admin_token,
        email="ukagent@test.com",
        role="uk_agent",
        name="UK Agent",
    )


@pytest_asyncio.fixture
async def customer_token(client: AsyncClient, admin_token: str) -> str:
    """Create a Customer user via the invite flow and return their access token."""
    return await _invite_and_register(
        client,
        admin_token,
        email="customer@test.com",
        role="customer",
        name="Customer",
    )


@pytest_asyncio.fixture
async def shipment(client: AsyncClient, admin_token: str) -> str:
    """Create a shipment as admin and return its ID as a string."""
    resp = await client.post(
        "/api/v1/shipments",
        json={"reference": "TEST-SHIP-001"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Shipment creation failed: {resp.json()}"
    return resp.json()["id"]


# ── State advancement helper ─────────────────────────────────────────────────


async def advance_to(
    client: AsyncClient,
    h: dict,
    target: str,
    ref: str = "ADV-001",
) -> tuple[str, dict]:
    """
    Drive a freshly created shipment to *target* state and return ``(sid, ctx)``.

    ``ctx`` holds IDs needed by tests that manipulate specific sub-resources:
      ``po_id``         — available from ``po_submitted`` onwards
      ``container_ids`` — available from ``bl_issued`` onwards

    Resource names (PO number, invoice number, etc.) are derived from *ref* so
    that multiple calls within a single test don't collide on unique constraints.

    Valid targets:
      ``"draft"``, ``"po_submitted"``, ``"invoice_received"``,
      ``"payment_confirmed"``, ``"bl_issued"``, ``"in_transit"``, ``"cleared"``
    """
    import uuid
    from datetime import date

    r = await client.post("/api/v1/shipments", json={"reference": ref}, headers=h)
    assert r.status_code == 200, f"advance_to({target!r}): create shipment failed: {r.json()}"
    sid = r.json()["id"]
    if target == "draft":
        return sid, {}

    r = await client.post(
        f"/api/v1/shipments/{sid}/po",
        json={
            "po_number": f"PO-{ref}",
            "po_date": "2026-01-10",
            "product_description": "Tiles",
            "quantity": "100",
            "quantity_unit": "boxes",
            "total_value": "10000.00",
            "currency": "USD",
        },
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): create PO failed: {r.json()}"
    po_id = r.json()["id"]

    r = await client.post(
        "/api/v1/documents/confirm",
        params={"entity_type": "purchase_order", "entity_id": po_id},
        json={"file_key": "k.pdf", "file_name": "po.pdf", "mime_type": "application/pdf"},
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): confirm doc failed: {r.json()}"

    r = await client.patch(f"/api/v1/shipments/{sid}/po/{po_id}/submit", headers=h)
    assert r.status_code == 200, f"advance_to({target!r}): submit PO failed: {r.json()}"
    if target == "po_submitted":
        return sid, {"po_id": po_id}

    r = await client.post(
        f"/api/v1/shipments/{sid}/invoice",
        json={
            "invoice_number": f"INV-{ref}",
            "invoice_date": "2026-01-15",
            "value": "10000.00",
            "currency": "USD",
        },
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, f"advance_to({target!r}): create invoice failed: {r.json()}"
    if target == "invoice_received":
        return sid, {"po_id": po_id}

    r = await client.post(
        f"/api/v1/shipments/{sid}/payments",
        json={
            "swift_ref": f"SW-{ref}",
            "payment_date": "2026-01-20",
            "amount": "10000.00",
            "currency": "USD",
            "payment_type": "full",
        },
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, f"advance_to({target!r}): add payment failed: {r.json()}"
    if target == "payment_confirmed":
        return sid, {"po_id": po_id}

    r = await client.post(
        f"/api/v1/shipments/{sid}/bl",
        json={
            "bl_number": f"BL-{ref}",
            "bl_date": "2026-01-25",
            "shipper_name": "Shipper",
            "consignee_name": "Consignee",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "Felixstowe",
            "containers": [
                {"container_number": f"TCKU{abs(hash(ref)) % 10**7:07d}"},
                {"container_number": f"MSCU{abs(hash(ref + '_2')) % 10**7:07d}"},
            ],
            "commodity_description": "Tiles",
            "gross_weight_kg": "5000.00",
        },
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): upload BL failed: {r.json()}"
    r2 = await client.get(f"/api/v1/shipments/{sid}/bl", headers=h)
    assert r2.status_code == 200, f"advance_to({target!r}): get BL failed: {r2.json()}"
    container_ids = [c["id"] for c in r2.json()["containers"]]
    if target == "bl_issued":
        return sid, {"po_id": po_id, "container_ids": container_ids}

    r = await client.post(
        f"/api/v1/shipments/{sid}/vessel",
        json={
            "vessel_name": "Test Vessel",
            "shipping_line": "TestLine",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "Felixstowe",
        },
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): create vessel failed: {r.json()}"
    r = await client.patch(
        f"/api/v1/shipments/{sid}/vessel/depart",
        json={"atd": "2026-02-01", "eta": "2026-02-14"},
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): confirm departure failed: {r.json()}"
    if target == "in_transit":
        return sid, {"po_id": po_id, "container_ids": container_ids}

    clearance_date = date.today().isoformat()
    for cid in container_ids:
        r = await client.put(
            f"/api/v1/shipments/{sid}/containers/{cid}/customs",
            json={"status": "cleared", "clearance_date": clearance_date},
            headers=h,
        )
        assert r.status_code == 200, f"advance_to({target!r}): upsert customs failed: {r.json()}"
    if target == "cleared":
        return sid, {"po_id": po_id, "container_ids": container_ids}

    raise ValueError(f"advance_to: unknown target state {target!r}")
