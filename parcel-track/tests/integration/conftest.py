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
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()


def token_to_user_id(token: str) -> str:
    claims = jose_jwt.get_unverified_claims(token)
    return claims["sub"]


async def _add_member(
    client: AsyncClient,
    admin_token: str,
    booking_id: str,
    user_token: str,
    role_override: str | None = None,
) -> None:
    """Add a user as a member of a booking via the admin API."""
    user_id = token_to_user_id(user_token)
    payload: dict = {"user_id": user_id}
    if role_override:
        payload["role_override"] = role_override

    resp = await client.post(
        f"/api/v1/bookings/{booking_id}/members",
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
    # Dispose the engine after each test. With sqlite+aiosqlite the pooled
    # connection runs a non-daemon background worker thread; if it is never
    # closed, the interpreter hangs at shutdown in threading._shutdown()
    # waiting to join it. dispose() closes the connection and stops that
    # thread. (CI uses Postgres/asyncpg, which has no such thread — this is
    # only load-bearing for the local SQLite default.)
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
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
    """Seed a second admin user directly — used to test admin bypass (no booking membership)."""
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
    return await _invite_and_register(
        client,
        admin_token,
        email="morocco@test.com",
        role="morocco_agent",
        name="Morocco Agent",
    )


@pytest_asyncio.fixture
async def uk_agent_token(client: AsyncClient, admin_token: str) -> str:
    return await _invite_and_register(
        client,
        admin_token,
        email="ukagent@test.com",
        role="uk_agent",
        name="UK Agent",
    )


@pytest_asyncio.fixture
async def customer_token(client: AsyncClient, admin_token: str) -> str:
    return await _invite_and_register(
        client,
        admin_token,
        email="customer@test.com",
        role="customer",
        name="Customer",
    )


@pytest_asyncio.fixture
async def booking(client: AsyncClient, admin_token: str) -> str:
    """Create a booking as admin and return its ID as a string."""
    resp = await client.post(
        "/api/v1/bookings",
        json={"reference": "TEST-BK-001"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Booking creation failed: {resp.json()}"
    return resp.json()["id"]


# Backwards-compatible alias — many older tests still spell this `shipment`.
@pytest_asyncio.fixture
async def shipment(booking: str) -> str:
    return booking


# ── State advancement helper ─────────────────────────────────────────────────


async def advance_to(
    client: AsyncClient,
    h: dict,
    target: str,
    ref: str = "ADV-001",
) -> tuple[str, dict]:
    """
    Drive a freshly created booking to *target* state and return ``(bid, ctx)``.

    ``ctx`` holds IDs needed by tests that manipulate specific sub-resources:
      ``po_id``         — available from ``po_submitted`` onwards
      ``container_ids`` — available from ``bl_issued`` onwards

    Resource names (PO number, invoice number, etc.) are derived from *ref* so
    that multiple calls within a single test don't collide on unique constraints.
    """
    import uuid
    from datetime import date

    # 1. Create the Booking.
    r = await client.post("/api/v1/bookings", json={"reference": ref}, headers=h)
    assert r.status_code == 200, f"advance_to({target!r}): create booking failed: {r.json()}"
    bid = r.json()["id"]
    if target == "draft":
        return bid, {}

    # 2. Create a standalone PO and attach it to the Booking.
    r = await client.post(
        "/api/v1/purchase-orders",
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
        f"/api/v1/bookings/{bid}/purchase-orders",
        json={"purchase_order_id": po_id},
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): link PO to booking failed: {r.json()}"

    # 3. Upload the PO's document so submit_po passes its document check.
    r = await client.post(
        "/api/v1/documents/confirm",
        params={"entity_type": "purchase_order", "entity_id": po_id},
        json={"file_key": "k.pdf", "file_name": "po.pdf", "mime_type": "application/pdf"},
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): confirm doc failed: {r.json()}"

    # 4. Submit the PO. This advances the linked booking to PO_SUBMITTED.
    r = await client.patch(f"/api/v1/purchase-orders/{po_id}/submit", headers=h)
    assert r.status_code == 200, f"advance_to({target!r}): submit PO failed: {r.json()}"
    if target == "po_submitted":
        return bid, {"po_id": po_id}

    # 5. Create the supplier Invoice against the PO. This advances the booking
    #    to INVOICE_RECEIVED (since every linked PO now has its invoice).
    r = await client.post(
        f"/api/v1/purchase-orders/{po_id}/invoice",
        json={
            "invoice_number": f"INV-{ref}",
            "invoice_date": "2026-01-15",
            "value": "10000.00",
            "currency": "USD",
        },
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, f"advance_to({target!r}): create invoice failed: {r.json()}"
    invoice_id = r.json()["id"]
    if target == "invoice_received":
        return bid, {"po_id": po_id, "invoice_id": invoice_id}

    # 6. Add a supplier payment against the invoice — advances to PAYMENT_CONFIRMED.
    r = await client.post(
        f"/api/v1/invoices/{invoice_id}/supplier-payments",
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
        return bid, {"po_id": po_id, "invoice_id": invoice_id}

    # 7. Upload the BL — advances to BL_ISSUED.
    r = await client.post(
        f"/api/v1/bookings/{bid}/bl",
        json={
            "bl_number": f"BL-{ref}",
            "bl_date": "2026-01-25",
            "shipper_name": "Shipper",
            "consignee_name": "Consignee",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "felixstowe",
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
    r2 = await client.get(f"/api/v1/bookings/{bid}/bl", headers=h)
    assert r2.status_code == 200, f"advance_to({target!r}): get BL failed: {r2.json()}"
    container_ids = [c["id"] for c in r2.json()["containers"]]
    if target == "bl_issued":
        return bid, {"po_id": po_id, "container_ids": container_ids}

    # 8. Create the vessel and confirm departure — advances to IN_TRANSIT.
    r = await client.post(
        f"/api/v1/bookings/{bid}/vessel",
        json={
            "vessel_name": "Test Vessel",
            "shipping_line": "TestLine",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "felixstowe",
        },
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): create vessel failed: {r.json()}"
    r = await client.patch(
        f"/api/v1/bookings/{bid}/vessel/depart",
        json={"atd": "2026-02-01", "eta": "2026-02-14"},
        headers=h,
    )
    assert r.status_code == 200, f"advance_to({target!r}): confirm departure failed: {r.json()}"
    if target == "in_transit":
        return bid, {"po_id": po_id, "container_ids": container_ids}

    # 9. Clear customs on every container — advances to CLEARED.
    clearance_date = date.today().isoformat()
    for cid in container_ids:
        r = await client.put(
            f"/api/v1/bookings/{bid}/containers/{cid}/customs",
            json={"status": "cleared", "clearance_date": clearance_date},
            headers=h,
        )
        assert r.status_code == 200, f"advance_to({target!r}): upsert customs failed: {r.json()}"
    if target == "cleared":
        return bid, {"po_id": po_id, "container_ids": container_ids}

    raise ValueError(f"advance_to: unknown target state {target!r}")
