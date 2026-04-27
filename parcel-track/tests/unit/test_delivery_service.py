"""Unit tests for DeliveryService — all-delivered → COMPLETE transition logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import DeliveryStatus, ShipmentStatus
from app.services.delivery_service import DeliveryService


def _make_point(status: DeliveryStatus) -> MagicMock:
    p = MagicMock()
    p.status = status
    return p


@pytest.mark.asyncio
async def test_all_delivered_triggers_complete_transition():
    """When the last point is delivered, shipment transitions to COMPLETE."""
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

    all_points_result = MagicMock()
    all_points_result.scalars.return_value = [_make_point(DeliveryStatus.DELIVERED)]

    db = AsyncMock()
    db.execute.side_effect = [point_result, all_points_result]

    shipment_mock = MagicMock()
    with patch("app.services.delivery_service.ShipmentService.get", return_value=shipment_mock), \
         patch("app.services.delivery_service.ShipmentService.transition_status") as mock_trans:

        from app.core.enums import UserRole
        actor.role = UserRole.ADMIN
        resp = await DeliveryService.update_status(
            db, uuid.uuid4(), uuid.uuid4(), body, actor, None
        )

    mock_trans.assert_awaited_once()
    assert mock_trans.call_args[0][2] == ShipmentStatus.COMPLETE
    assert "DELIVERED" in resp["message"]


@pytest.mark.asyncio
async def test_not_all_delivered_no_transition():
    """If one point is still pending, shipment should not complete."""
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

    all_points_result = MagicMock()
    all_points_result.scalars.return_value = [
        _make_point(DeliveryStatus.DELIVERED),
        _make_point(DeliveryStatus.SCHEDULED),  # still pending
    ]

    db = AsyncMock()
    db.execute.side_effect = [point_result, all_points_result]

    with patch("app.services.delivery_service.ShipmentService.transition_status") as mock_trans:
        from app.core.enums import UserRole
        actor.role = UserRole.ADMIN
        await DeliveryService.update_status(db, uuid.uuid4(), uuid.uuid4(), body, actor, None)

    mock_trans.assert_not_called()


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

    with patch("app.services.delivery_service.ShipmentService.transition_status") as mock_trans:
        from app.core.enums import UserRole
        actor.role = UserRole.ADMIN
        await DeliveryService.update_status(db, uuid.uuid4(), uuid.uuid4(), body, actor, None)

    assert point.status == DeliveryStatus.AWAITING_SCHEDULE
    assert schedule.failure_reason == "No one home"
    mock_trans.assert_not_called()
