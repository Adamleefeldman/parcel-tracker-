"""
Regression tests for the after-commit push dispatch hook.

NotificationService.send must NOT enqueue a Celery push task if the
caller's outer transaction rolls back — otherwise the worker re-reads
a notification id that does not exist.
"""

from unittest.mock import patch

import pytest
import pytest_asyncio

from app.core.enums import NotificationType, UserRole
from app.core.security import hash_password
from app.db.models import User
from app.services.notification_service import NotificationService
from tests.integration.conftest import TestSession


@pytest_asyncio.fixture
async def push_user() -> User:
    async with TestSession() as db:
        user = User(
            email="push@test.com",
            hashed_password=hash_password("pass123456"),
            name="Push User",
            role=UserRole.CUSTOMER,
            expo_push_token="ExponentPushToken[xxx]",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
def push_spy():
    """Replace the autouse no-op stub with a spy that records calls."""
    from app.background import tasks as bg_tasks

    calls: list[tuple] = []

    def _record(*args, **kwargs):
        calls.append((args, kwargs))

    with patch.object(bg_tasks.send_push_notification, "delay", _record):
        yield calls


class TestPushDispatchTransactionSafety:
    async def test_push_enqueued_after_commit(self, push_user: User, push_spy: list):
        async with TestSession() as db:
            await NotificationService.send(
                db=db,
                user_id=push_user.id,
                booking_id=None,
                notification_type=NotificationType.PO_SUBMITTED,
            )
            # Before commit: no dispatch
            assert push_spy == []
            await db.commit()

        # After commit: exactly one dispatch
        assert len(push_spy) == 1

    async def test_push_not_enqueued_on_rollback(self, push_user: User, push_spy: list):
        async with TestSession() as db:
            await NotificationService.send(
                db=db,
                user_id=push_user.id,
                booking_id=None,
                notification_type=NotificationType.PO_SUBMITTED,
            )
            await db.rollback()

        assert push_spy == []
