"""Unit tests for AuditService.record (master-data audit helper)."""

import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.db.models import AuditLog
from app.services.audit_service import AuditService


def test_record_string_keyed_entity():
    db = MagicMock()
    actor_id = uuid.uuid4()

    AuditService.record(
        db,
        actor_id=actor_id,
        action="currency.created",
        entity_type="currency",
        entity_code="AED",
        new={"code": "AED", "name": "UAE Dirham"},
        ip="1.2.3.4",
    )

    db.add.assert_called_once()
    row = db.add.call_args.args[0]
    assert isinstance(row, AuditLog)
    assert row.entity_type == "currency"
    assert row.entity_code == "AED"
    assert row.entity_id is None
    assert row.actor_id == actor_id
    assert json.loads(row.new_value) == {"code": "AED", "name": "UAE Dirham"}
    assert row.old_value is None
    assert row.ip_address == "1.2.3.4"


def test_record_uuid_keyed_entity():
    db = MagicMock()
    entity_id = uuid.uuid4()

    AuditService.record(
        db,
        actor_id=uuid.uuid4(),
        action="booking.updated",
        entity_type="booking",
        entity_id=entity_id,
        old={"status": "DRAFT"},
        new={"status": "PO_SUBMITTED"},
    )

    row = db.add.call_args.args[0]
    assert row.entity_id == entity_id
    assert row.entity_code is None
    assert json.loads(row.old_value) == {"status": "DRAFT"}


def test_record_requires_exactly_one_ref():
    db = MagicMock()

    with pytest.raises(ValueError):
        AuditService.record(db, actor_id=uuid.uuid4(), action="x", entity_type="y")  # neither

    with pytest.raises(ValueError):
        AuditService.record(
            db,
            actor_id=uuid.uuid4(),
            action="x",
            entity_type="y",
            entity_id=uuid.uuid4(),
            entity_code="AED",
        )  # both

    db.add.assert_not_called()
