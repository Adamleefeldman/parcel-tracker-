import pytest
import pytest_asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from jose import jwt as jose_jwt

from app.main import app
from app.db.database import Base, get_db
from app.core.enums import UserRole

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DB_URL, echo=False)
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


# ── Infrastructure mocks ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_storage_service():
    """
    Prevent every test from reaching AWS S3.

    StorageService has three methods that talk to the network:
      - generate_file_key  → builds an S3 object key string
      - get_upload_url     → calls boto3 to generate a pre-signed PUT URL
      - get_download_url   → calls boto3 to generate a pre-signed GET URL

    Tests that exercise document-related flows (e.g. submit_po) need a
    Document row to exist in the DB.  That row is created via the
    POST /documents/confirm endpoint, which internally calls get_download_url.
    Without this mock that call crashes immediately because there are no
    AWS credentials in the test environment.

    Using autouse=True means every test in this suite is protected
    automatically — no individual test needs to remember to opt in.
    """
    with patch(
        "app.services.storage_service.StorageService.generate_file_key",
        return_value="test/uploads/fake-key.pdf",
    ), patch(
        "app.services.storage_service.StorageService.get_upload_url",
        return_value="https://fake-s3.example.com/upload",
    ), patch(
        "app.services.storage_service.StorageService.get_download_url",
        return_value="https://fake-s3.example.com/download",
    ):
        yield


# ── Shared helper functions ───────────────────────────────────────────────────

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
        from app.db.models import User
        from app.core.security import hash_password
        admin = User(
            email="admin@test.com",
            hashed_password=hash_password("adminpass123"),
            name="Test Admin",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.commit()

    resp = await client.post("/api/v1/auth/login", json={
        "email": "admin@test.com",
        "password": "adminpass123",
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def admin_refresh_token(client: AsyncClient):
    """Seed a second admin user and return their refresh token."""
    async with TestSession() as db:
        from app.db.models import User
        from app.core.security import hash_password
        admin = User(
            email="admin2@test.com",
            hashed_password=hash_password("adminpass123"),
            name="Test Admin 2",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.commit()

    resp = await client.post("/api/v1/auth/login", json={
        "email": "admin2@test.com",
        "password": "adminpass123",
    })
    assert resp.status_code == 200
    return resp.json()["refresh_token"]


@pytest_asyncio.fixture
async def second_admin_token(client: AsyncClient):
    """Seed a second admin user directly — used to test admin bypass (no shipment membership)."""
    async with TestSession() as db:
        from app.db.models import User
        from app.core.security import hash_password
        admin = User(
            email="admin3@test.com",
            hashed_password=hash_password("adminpass123"),
            name="Test Admin 3",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.commit()

    resp = await client.post("/api/v1/auth/login", json={
        "email": "admin3@test.com",
        "password": "adminpass123",
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _invite_and_register(client: AsyncClient, admin_token: str, email: str, role: str, name: str) -> str:
    """Helper: admin sends invite, user accepts, returns the new user's access token."""
    invite_resp = await client.post(
        "/api/v1/auth/invite",
        json={"email": email, "role": role},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert invite_resp.status_code == 200, f"Invite failed: {invite_resp.json()}"
    token = invite_resp.json()["invite_token"]

    accept_resp = await client.post("/api/v1/auth/accept-invite", json={
        "token": token,
        "name": name,
        "password": "testpass123",
    })
    assert accept_resp.status_code == 200, f"Accept invite failed: {accept_resp.json()}"
    return accept_resp.json()["access_token"]


@pytest_asyncio.fixture
async def morocco_agent_token(client: AsyncClient, admin_token: str) -> str:
    """Create a Morocco Agent user via the invite flow and return their access token."""
    return await _invite_and_register(
        client, admin_token,
        email="morocco@test.com",
        role="morocco_agent",
        name="Morocco Agent",
    )


@pytest_asyncio.fixture
async def uk_agent_token(client: AsyncClient, admin_token: str) -> str:
    """Create a UK Agent user via the invite flow and return their access token."""
    return await _invite_and_register(
        client, admin_token,
        email="ukagent@test.com",
        role="uk_agent",
        name="UK Agent",
    )


@pytest_asyncio.fixture
async def customer_token(client: AsyncClient, admin_token: str) -> str:
    """Create a Customer user via the invite flow and return their access token."""
    return await _invite_and_register(
        client, admin_token,
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
