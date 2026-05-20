"""Unit tests for ShipmentLegService (P1.1).

The load-bearing logic is `leg_index` auto-assignment in `add()` and the
404 paths. Integration tests in `tests/integration/test_shipment_legs.py`
cover the end-to-end route behaviour against a real database.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.schemas.schemas import ShipmentLegCreate, ShipmentLegUpdate
from app.services.shipment_leg_service import ShipmentLegService


def _one(value):
    """Result mock whose scalar_one_or_none() returns `value`."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


def _scalar(value):
    """Result mock whose scalar() returns `value`."""
    m = MagicMock()
    m.scalar.return_value = value
    return m


def _scalars(items):
    """Result mock whose scalars().all() returns `items`."""
    m = MagicMock()
    m.scalars.return_value.all.return_value = items
    return m


def _create_body(leg_index: int | None = None) -> ShipmentLegCreate:
    return ShipmentLegCreate(
        vessel_name="MAERSK NEWARK",
        voyage_number="V602E",
        shipping_line="Maersk",
        port_from="Casablanca",
        port_to="Algeciras",
        leg_index=leg_index,
    )


@pytest.mark.asyncio
async def test_add_auto_assigns_first_leg_index():
    """No existing legs → first leg gets leg_index 1."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _one(MagicMock()),  # booking lookup → exists
            _scalar(None),  # max(leg_index) → none yet
        ]
    )

    leg = await ShipmentLegService.add(db, uuid.uuid4(), _create_body(), MagicMock(), None)

    assert leg.leg_index == 1
    db.add.assert_called()  # leg + audit log both added


@pytest.mark.asyncio
async def test_add_auto_assigns_next_leg_index():
    """Existing max leg_index 2 → next leg gets 3."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _one(MagicMock()),  # booking lookup
            _scalar(2),  # max(leg_index)
        ]
    )

    leg = await ShipmentLegService.add(db, uuid.uuid4(), _create_body(), MagicMock(), None)

    assert leg.leg_index == 3


@pytest.mark.asyncio
async def test_add_respects_explicit_leg_index():
    """An explicit leg_index is used verbatim — no max() query is issued."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(side_effect=[_one(MagicMock())])  # only the booking lookup

    leg = await ShipmentLegService.add(
        db, uuid.uuid4(), _create_body(leg_index=5), MagicMock(), None
    )

    assert leg.leg_index == 5
    assert db.execute.await_count == 1  # max() query skipped


@pytest.mark.asyncio
async def test_add_booking_not_found():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_one(None)])  # booking lookup → missing

    with pytest.raises(HTTPException) as exc:
        await ShipmentLegService.add(db, uuid.uuid4(), _create_body(), MagicMock(), None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_add_duplicate_leg_index_conflicts():
    """A leg_index collision surfaces as a 409, not a raw IntegrityError."""
    db = MagicMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.execute = AsyncMock(side_effect=[_one(MagicMock())])

    with pytest.raises(HTTPException) as exc:
        await ShipmentLegService.add(db, uuid.uuid4(), _create_body(leg_index=1), MagicMock(), None)
    assert exc.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_sets_ata():
    """A partial update applies only the supplied fields."""
    from app.db.models import ShipmentLeg

    booking_id = uuid.uuid4()
    leg = ShipmentLeg(
        id=uuid.uuid4(),
        booking_id=booking_id,
        leg_index=1,
        vessel_name="MADRID MAERSK",
        shipping_line="Maersk",
        port_from="Algeciras",
        port_to="London Gateway",
    )
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(side_effect=[_one(leg)])

    updated = await ShipmentLegService.update(
        db,
        booking_id,
        leg.id,
        ShipmentLegUpdate(ata=date(2026, 5, 18)),
        MagicMock(),
        None,
    )

    assert updated.ata == date(2026, 5, 18)
    assert updated.vessel_name == "MADRID MAERSK"  # untouched
    db.add.assert_called_once()  # audit log row


@pytest.mark.asyncio
async def test_update_leg_not_found():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_one(None)])

    with pytest.raises(HTTPException) as exc:
        await ShipmentLegService.update(
            db,
            uuid.uuid4(),
            uuid.uuid4(),
            ShipmentLegUpdate(ata=date(2026, 5, 18)),
            MagicMock(),
            None,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_for_booking_returns_legs():
    db = MagicMock()
    legs = [MagicMock(), MagicMock()]
    db.execute = AsyncMock(side_effect=[_one(MagicMock()), _scalars(legs)])

    result = await ShipmentLegService.list_for_booking(db, uuid.uuid4())

    assert result == legs


@pytest.mark.asyncio
async def test_list_for_booking_not_found():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_one(None)])

    with pytest.raises(HTTPException) as exc:
        await ShipmentLegService.list_for_booking(db, uuid.uuid4())
    assert exc.value.status_code == 404
