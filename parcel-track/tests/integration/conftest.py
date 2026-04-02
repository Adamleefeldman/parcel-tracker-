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
