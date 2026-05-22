"""Unit tests for PortTemplateService.apply_to_booking (P1.3).

`apply_to_booking` fills a booking's P1.2 free-day / rate fields from the
port's template, but must never overwrite values that are already set.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.enums import UKPort
from app.db.models import Booking, PortTemplate
from app.services.port_template_service import PortTemplateService


def _one(value):
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


@pytest.mark.asyncio
async def test_apply_fills_only_unset_fields():
    template = PortTemplate(
        port=UKPort.FELIXSTOWE,
        free_days_detention=7,
        free_days_demurrage=5,
        detention_rate_gbp_after=Decimal("100.00"),
        demurrage_rate_gbp_after=Decimal("150.00"),
    )
    booking = Booking(
        free_days_detention=None,  # unset → filled from template
        free_days_demurrage=3,  # already set → preserved
        detention_rate_gbp_after=None,  # unset → filled
        demurrage_rate_gbp_after=None,  # unset → filled
    )
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(side_effect=[_one(template), _one(booking)])

    await PortTemplateService.apply_to_booking(db, uuid.uuid4(), UKPort.FELIXSTOWE)

    assert booking.free_days_detention == 7
    assert booking.free_days_demurrage == 3  # NOT overwritten
    assert booking.detention_rate_gbp_after == Decimal("100.00")
    assert booking.demurrage_rate_gbp_after == Decimal("150.00")


@pytest.mark.asyncio
async def test_apply_noop_when_no_template():
    booking = Booking(free_days_demurrage=None)
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(side_effect=[_one(None)])  # no template for this port

    await PortTemplateService.apply_to_booking(db, uuid.uuid4(), UKPort.TILBURY)

    assert booking.free_days_demurrage is None
