"""Unit tests for DeliveryService — all-delivered → COMPLETE transition logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import BookingStatus, DeliveryStatus
from app.services.delivery_service import DeliveryService


def _make_point(status: DeliveryStatus) -> MagicMock:
    p = MagicMock()
    p.status = status
    return p


@pytest.mark.asyncio
async def test_delivered_attempts_complete_transition():
    """A delivery DELIVERED write always attempts the COMPLETE transition.

    P0.4 lifecycle: the actual graduation depends on whether every container
    has reached BANKED — that's the booking-level precondition's job. From
    the delivery service's perspective, DELIVERED just fans out
    ContainerLifecycleService.recompute calls and pokes the state machine.
    """
    import uuid

    actor = MagicMock()

    body = MagicMock()
    body.status = DeliveryStatus.DELIVERED.value
    body.failure_reason = None

    point = MagicMock()
    point.id = uuid.uuid4()
    point.schedule = None
    point.customer_user_id = None

    point_result = MagicMock()
    point_result.scalar_one_or_none.return_value = point

    # Assignments lookup returns one container id row.
    assignments_result = MagicMock()
    assignments_result.all.return_value = [(uuid.uuid4(),)]

    db = AsyncMock()
    db.execute.side_effect = [point_result, assignments_result]

    booking_mock = MagicMock()
    with (
        patch(
            "app.services.delivery_service.ContainerLifecycleService.recompute",
            new_callable=AsyncMock,
        ),
        patch("app.services.delivery_service.BookingService.get", return_value=booking_mock),
        patch("app.services.delivery_service.BookingService.transition_status") as mock_trans,
    ):
        from app.core.enums import UserRole

        actor.role = UserRole.ADMIN
        resp = await DeliveryService.update_status(
            db, uuid.uuid4(), uuid.uuid4(), body, actor, None
        )

    mock_trans.assert_awaited_once()
    assert mock_trans.call_args[0][2] == BookingStatus.COMPLETE
    assert "DELIVERED" in resp["message"]


@pytest.mark.asyncio
async def test_delivered_with_unfinished_lifecycle_swallows_precondition_failure():
    """When the booking-level COMPLETE precondition rejects (containers
    not yet BANKED), the delivery write still succeeds — the HTTPException
    is swallowed so the caller doesn't see a 400 for a successful delivery.
    """
    import uuid

    from fastapi import HTTPException

    actor = MagicMock()

    body = MagicMock()
    body.status = DeliveryStatus.DELIVERED.value
    body.failure_reason = None

    point = MagicMock()
    point.id = uuid.uuid4()
    point.schedule = None
    point.customer_user_id = None

    point_result = MagicMock()
    point_result.scalar_one_or_none.return_value = point

    assignments_result = MagicMock()
    assignments_result.all.return_value = [(uuid.uuid4(),)]

    db = AsyncMock()
    db.execute.side_effect = [point_result, assignments_result]

    booking_mock = MagicMock()
    with (
        patch(
            "app.services.delivery_service.ContainerLifecycleService.recompute",
            new_callable=AsyncMock,
        ),
        patch("app.services.delivery_service.BookingService.get", return_value=booking_mock),
        patch(
            "app.services.delivery_service.BookingService.transition_status",
            side_effect=HTTPException(400, "container(s) not yet banked"),
        ),
    ):
        from app.core.enums import UserRole

        actor.role = UserRole.ADMIN
        # Must not propagate the 400 — delivery itself succeeded.
        resp = await DeliveryService.update_status(
            db, uuid.uuid4(), uuid.uuid4(), body, actor, None
        )

    assert "DELIVERED" in resp["message"]


@pytest.mark.asyncio
async def test_failed_delivery_resets_to_awaiting_schedule():
    """A FAILED status resets the point to AWAITING_SCHEDULE for rescheduling."""
    import uuid

    actor = MagicMock()

    body = MagicMock()
    body.status = DeliveryStatus.FAILED.value
    body.failure_reason = "No one home"

    schedule = MagicMock()
    point = MagicMock()
    point.id = uuid.uuid4()
    point.schedule = schedule
    point.customer_user_id = None

    point_result = MagicMock()
    point_result.scalar_one_or_none.return_value = point

    db = AsyncMock()
    db.execute.side_effect = [point_result]

    with patch("app.services.delivery_service.BookingService.transition_status") as mock_trans:
        from app.core.enums import UserRole

        actor.role = UserRole.ADMIN
        await DeliveryService.update_status(db, uuid.uuid4(), uuid.uuid4(), body, actor, None)

    assert point.status == DeliveryStatus.AWAITING_SCHEDULE
    assert schedule.failure_reason == "No one home"
    mock_trans.assert_not_called()
