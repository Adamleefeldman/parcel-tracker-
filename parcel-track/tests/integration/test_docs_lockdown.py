"""
D1 — /docs lockdown.

The built-in FastAPI docs endpoints are remounted behind ``docs_guard`` in
``app/main.py``. The guard reads ``settings.is_production`` per-request:
prod requires an admin token, dev/test stays open.

These tests flip ``APP_ENV`` on the cached Settings instance via monkeypatch
to exercise the prod path without restarting the app.
"""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings

DOCS_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.fixture
def prod_env(monkeypatch):
    """Flip the cached Settings instance into production mode for one test."""
    monkeypatch.setattr(get_settings(), "APP_ENV", "production")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", DOCS_PATHS)
async def test_docs_unauthenticated_in_prod_returns_401(client: AsyncClient, prod_env, path: str):
    resp = await client.get(path)
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", DOCS_PATHS)
async def test_docs_non_admin_in_prod_returns_403(
    client: AsyncClient, prod_env, customer_token: str, path: str
):
    resp = await client.get(path, headers={"Authorization": f"Bearer {customer_token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("path", DOCS_PATHS)
async def test_docs_admin_in_prod_returns_200(
    client: AsyncClient, prod_env, admin_token: str, path: str
):
    resp = await client.get(path, headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("path", DOCS_PATHS)
async def test_docs_open_unauthenticated_in_dev(client: AsyncClient, path: str):
    resp = await client.get(path)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_openapi_schema_not_empty_in_dev(client: AsyncClient):
    """Guards against handler bugs that would return an empty/stripped schema."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("paths"), dict)
    assert data["paths"], "openapi schema must list at least one path"


@pytest.mark.asyncio
async def test_openapi_schema_not_empty_for_admin_in_prod(
    client: AsyncClient, prod_env, admin_token: str
):
    resp = await client.get("/openapi.json", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("paths"), "admin must see the full schema in prod"
