"""p1a.0: master-data audit support (string-keyed entities)

Revision ID: a0b1c2d3e4f5
Revises: a6b7c8d9e0f1
Create Date: 2026-07-02 09:00:00.000000

`AuditLog.entity_id` was `UUID NOT NULL`, built for UUID-keyed rows (bookings,
containers…). The Data-Foundation master data is string-keyed — currencies.code,
incoterms.code — so those rows cannot be referenced by a UUID. This migration
makes the audit table able to record string-keyed entities:

  * entity_id   -> nullable (UUID-keyed rows keep using it)
  * entity_code -> new nullable String(40) (for string-keyed master data)
  * CHECK: exactly one of (entity_id, entity_code) is set

Additive and safe: every existing audit row has entity_id set and entity_code
NULL, so the new exactly-one CHECK holds for all of them with no backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("entity_code", sa.String(length=40), nullable=True))
    op.alter_column(
        "audit_logs",
        "entity_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_audit_logs_entity_ref",
        "audit_logs",
        "(entity_id IS NOT NULL) <> (entity_code IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_logs_entity_ref", "audit_logs", type_="check")
    # Re-tighten entity_id to NOT NULL. Safe only while no string-keyed audit
    # rows exist (those have a NULL entity_id). Audit rows are never deleted, so
    # if such history exists this will fail rather than silently lose it.
    op.alter_column(
        "audit_logs",
        "entity_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("audit_logs", "entity_code")
