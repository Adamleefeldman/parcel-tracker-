"""Unit tests for CustomsService — cascade and transition logic."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import ContainerStatus, CustomsStatus, PortStatus, ShipmentStatus, UserRole
from app.services.customs_service import CustomsService


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


def _make_db(record, container, all_containers: list, refreshed_record):
    db = AsyncMock()
    record_result = MagicMock()
    record_result.scalar_one_or_none.return_value = record

    container_result = MagicMock()
    container_result.scalar_one_or_none.return_value = container

    refreshed = MagicMock()
    refreshed.scalar_one.return_value = refreshed_record

    db.execute.side_effect = [
        record_result,
        container_result,
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

    db = _make_db(record, container, [_make_container(ContainerStatus.CLEARED)], record)

    with patch("app.services.customs_service.NotificationService.notify_shipment_roles"), \
         patch("app.services.customs_service.ShipmentService.get", return_value=MagicMock()), \
         patch("app.services.customs_service.ShipmentService.transition_status"):

        await CustomsService.upsert(
            db, uuid.uuid4(), uuid.uuid4(), _make_body(CustomsStatus.CLEARED), actor, None
        )

    assert container.status == ContainerStatus.CLEARED
    assert container.port_status == PortStatus.RELEASED


@pytest.mark.asyncio
async def test_all_containers_cleared_triggers_shipment_transition():
    """When the last container clears, shipment transitions to CLEARED."""
    actor = MagicMock()
    actor.role = UserRole.ADMIN

    container = MagicMock()
    container.container_number = "CNTR001"
    record = MagicMock()
    record.id = uuid.uuid4()

    db = _make_db(record, container, [_make_container(ContainerStatus.CLEARED)], record)

    shipment_mock = MagicMock()
    with patch("app.services.customs_service.NotificationService.notify_shipment_roles"), \
         patch("app.services.customs_service.ShipmentService.get", return_value=shipment_mock), \
         patch("app.services.customs_service.ShipmentService.transition_status") as mock_trans:

        await CustomsService.upsert(
            db, uuid.uuid4(), uuid.uuid4(), _make_body(CustomsStatus.CLEARED), actor, None
        )

    mock_trans.assert_awaited_once()
    assert mock_trans.call_args[0][2] == ShipmentStatus.CLEARED


@pytest.mark.asyncio
async def test_not_all_cleared_does_not_trigger_transition():
    """If one container is still pending, shipment should not transition."""
    actor = MagicMock()
    actor.role = UserRole.ADMIN

    container = MagicMock()
    container.container_number = "CNTR001"
    record = MagicMock()
    record.id = uuid.uuid4()

    db = _make_db(
        record,
        container,
        [_make_container(ContainerStatus.CLEARED), _make_container(ContainerStatus.ON_HOLD)],
        record,
    )

    with patch("app.services.customs_service.NotificationService.notify_shipment_roles"), \
         patch("app.services.customs_service.ShipmentService.transition_status") as mock_trans:

        await CustomsService.upsert(
            db, uuid.uuid4(), uuid.uuid4(), _make_body(CustomsStatus.CLEARED), actor, None
        )

    mock_trans.assert_not_called()
