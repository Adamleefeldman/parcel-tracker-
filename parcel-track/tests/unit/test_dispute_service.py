"""Unit tests for ContainerService.open_dispute / acknowledge_dispute (P2.1).

Covers the role + 404 + 400 guards; full happy-path behaviour is covered by
the integration tests in tests/integration/test_disputes.py.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.enums import ContainerLifecycleStatus, UserRole
from app.db.models import Container
from app.services.container_service import ContainerService


def _one(value):
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


def _user(role: UserRole) -> MagicMock:
    u = MagicMock()
    u.role = role
    u.id = uuid.uuid4()
    return u


@pytest.mark.asyncio
async def test_open_dispute_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        await ContainerService.open_dispute(
            MagicMock(), uuid.uuid4(), "broken seal", _user(UserRole.UK_AGENT), None
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_open_dispute_404_when_container_missing():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_one(None)])
    with pytest.raises(HTTPException) as exc:
        await ContainerService.open_dispute(db, uuid.uuid4(), "reason", _user(UserRole.ADMIN), None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_acknowledge_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        await ContainerService.acknowledge_dispute(
            MagicMock(), uuid.uuid4(), _user(UserRole.UK_AGENT), None
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_acknowledge_400_when_not_currently_disputed():
    """Can't acknowledge what isn't disputed."""
    db = MagicMock()
    container = Container(lifecycle_status=ContainerLifecycleStatus.DELIVERED)
    db.execute = AsyncMock(side_effect=[_one(container)])
    with pytest.raises(HTTPException) as exc:
        await ContainerService.acknowledge_dispute(db, uuid.uuid4(), _user(UserRole.ADMIN), None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_acknowledge_404_when_container_missing():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_one(None)])
    with pytest.raises(HTTPException) as exc:
        await ContainerService.acknowledge_dispute(db, uuid.uuid4(), _user(UserRole.ADMIN), None)
    assert exc.value.status_code == 404
