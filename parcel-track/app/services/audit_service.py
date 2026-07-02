"""Central audit-log helper (Data-Foundation).

Master-data services (currencies, and later incoterms, warehouses, …) and any
other write path record "who changed what" through `AuditService.record`. It
supports both UUID-keyed entities (bookings, containers) and string-keyed master
data (currencies.code) via the `entity_id` / `entity_code` split on `AuditLog`.

The helper only *stages* the row (`db.add`); the caller owns the transaction, so
the audit row commits atomically with the mutation it describes (`get_db` commits
at request end).
"""

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


class AuditService:
    @staticmethod
    def record(
        db: AsyncSession,
        *,
        actor_id: uuid.UUID,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        entity_code: str | None = None,
        old: dict[str, Any] | None = None,
        new: dict[str, Any] | None = None,
        ip: str | None = None,
        booking_id: uuid.UUID | None = None,
    ) -> None:
        """Stage an AuditLog row. Exactly one of entity_id / entity_code must be set."""
        if (entity_id is None) == (entity_code is None):
            raise ValueError("record() requires exactly one of entity_id or entity_code")
        db.add(
            AuditLog(
                booking_id=booking_id,
                actor_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_code=entity_code,
                old_value=json.dumps(old) if old is not None else None,
                new_value=json.dumps(new) if new is not None else None,
                ip_address=ip,
            )
        )
