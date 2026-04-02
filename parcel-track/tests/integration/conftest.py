import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

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
