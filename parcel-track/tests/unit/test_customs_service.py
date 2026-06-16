"""Unit tests for CustomsService — cascade and transition logic.

Container ownership (container belongs to the path booking) is enforced by
``ContainerService.get_in_booking`` and patched out here so these tests stay
focused on the customs cascade. After that helper, ``upsert`` issues three
``db.execute`` calls on the CLEARED path: customs-record fetch, all-containers
query, refreshed-record fetch.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.enums import BookingStatus, ContainerStatus, CustomsStatus, PortStatus, UserRole
from app.services.customs_service import CustomsService

_GET_IN_BOOKING = "app.services.customs_service.ContainerService.get_in_booking"


def _make_container(status: ContainerStatus) -> MagicMock:
    c = MagicMock()
    c.status = status
    return c


def _scalars_mock(items: list) -> MagicMock:
    """Return a mock whose .scalars().all() yields items."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _make_db(record, all_containers: list, refreshed_record):
    """Mock db.execute for the CLEARED path: record fetch, all-containers, refreshed."""
    db = AsyncMock()
    record_result = MagicMock()
    record_result.scalar_one_or_none.return_value = record

    refreshed = MagicMock()
    refreshed.scalar_one.return_value = refreshed_record

    db.execute.side_effect = [
        record_result,
        _scalars_mock(all_containers),
        refreshed,
    ]
    return db


def _make_body(status: CustomsStatus) -> MagicMock:
    body = MagicMock()
    body.status = status.value
    body.clearance_date = None
    body.hold_reason = None
    body.hmrc_ref = None
    body.duty_paid = None
    return body


@pytest.mark.asyncio
async def test_cleared_cascades_to_container_fields():
    """When customs status is CLEARED, container status and port_status are updated."""
    actor = MagicMock()
    actor.role = UserRole.ADMIN

    container = MagicMock()
    container.container_number = "CNTR001"
    record = MagicMock()
    record.id = uuid.uuid4()

    db = _make_db(record, [_make_container(ContainerStatus.CLEARED)], record)

    with (
        patch(_GET_IN_BOOKING, new_callable=AsyncMock, return_value=container),
        patch("app.services.customs_service.NotificationService.notify_booking_roles"),
        patch("app.services.customs_service.BookingService.get", return_value=MagicMock()),
        patch("app.services.customs_service.BookingService.transition_status"),
        patch(
            "app.services.customs_service.ContainerLifecycleService.recompute",
            new_callable=AsyncMock,
        ),
    ):
        await CustomsService.upsert(
            db, uuid.uuid4(), uuid.uuid4(), _make_body(CustomsStatus.CLEARED), actor, None
        )

    assert container.status == ContainerStatus.CLEARED
    assert container.port_status == PortStatus.RELEASED


@pytest.mark.asyncio
async def test_all_containers_cleared_triggers_booking_transition():
    """When the last container clears, booking transitions to CLEARED."""
    actor = MagicMock()
    actor.role = UserRole.ADMIN

    container = MagicMock()
    container.container_number = "CNTR001"
    record = MagicMock()
    record.id = uuid.uuid4()

    db = _make_db(record, [_make_container(ContainerStatus.CLEARED)], record)

    booking_mock = MagicMock()
    with (
        patch(_GET_IN_BOOKING, new_callable=AsyncMock, return_value=container),
        patch("app.services.customs_service.NotificationService.notify_booking_roles"),
        patch("app.services.customs_service.BookingService.get", return_value=booking_mock),
        patch("app.services.customs_service.BookingService.transition_status") as mock_trans,
        patch(
            "app.services.customs_service.ContainerLifecycleService.recompute",
            new_callable=AsyncMock,
        ),
    ):
        await CustomsService.upsert(
            db, uuid.uuid4(), uuid.uuid4(), _make_body(CustomsStatus.CLEARED), actor, None
        )

    mock_trans.assert_awaited_once()
    assert mock_trans.call_args[0][2] == BookingStatus.CLEARED


@pytest.mark.asyncio
async def test_not_all_cleared_does_not_trigger_transition():
    """If one container is still pending, booking should not transition."""
    actor = MagicMock()
    actor.role = UserRole.ADMIN

    container = MagicMock()
    container.container_number = "CNTR001"
    record = MagicMock()
    record.id = uuid.uuid4()

    db = _make_db(
        record,
        [_make_container(ContainerStatus.CLEARED), _make_container(ContainerStatus.ON_HOLD)],
        record,
    )

    with (
        patch(_GET_IN_BOOKING, new_callable=AsyncMock, return_value=container),
        patch("app.services.customs_service.NotificationService.notify_booking_roles"),
        patch("app.services.customs_service.BookingService.transition_status") as mock_trans,
        patch(
            "app.services.customs_service.ContainerLifecycleService.recompute",
            new_callable=AsyncMock,
        ),
    ):
        await CustomsService.upsert(
            db, uuid.uuid4(), uuid.uuid4(), _make_body(CustomsStatus.CLEARED), actor, None
        )

    mock_trans.assert_not_called()


@pytest.mark.asyncio
async def test_missing_or_cross_booking_container_raises_404():
    """If the container is missing, RLS-hidden, or belongs to a different booking,
    the ownership guard raises 404 before any customs write."""
    actor = MagicMock()
    actor.role = UserRole.ADMIN

    db = AsyncMock()

    with (
        patch(
            _GET_IN_BOOKING,
            new_callable=AsyncMock,
            side_effect=HTTPException(404, "Container not found"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await CustomsService.upsert(
            db, uuid.uuid4(), uuid.uuid4(), _make_body(CustomsStatus.CLEARED), actor, None
        )

    assert exc_info.value.status_code == 404
    assert "Container not found" in exc_info.value.detail
    db.execute.assert_not_called()
