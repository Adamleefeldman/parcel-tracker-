"""p0 fix: reconcile notificationtype enum labels with the model

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-14 09:00:00.000000

`Notification.type` is bound to PostgreSQL by member *name* (uppercase) via the
default `SAEnum(NotificationType)`. Two model members were never added to the
Postgres `notificationtype` type:

  * PO_SUBMITTED       — fired on every PO submit (po_service)
  * VESSEL_APPROACHING — fired by the VesselFinder poller (vessel_poll_service)

and two more were added by `d3e4f5a6b7c8` in the wrong case (`ar_aging_alert` /
`demurrage_warning` — value-case, not the name-case SAEnum writes), so the daily
A/R-aging and demurrage alerts also fail to insert.

On PostgreSQL each such insert raises `DataError` and rolls back the whole request
transaction — e.g. submitting any purchase order 500s. The bug is invisible to the
test suite because it builds the schema from `Base.metadata.create_all` (the model's
full uppercase enum), not from this migration chain.

This migration adds the two missing labels and renames the two mis-cased ones so the
Postgres type matches the model exactly. `ADD VALUE` is PG12+ transaction-safe as long
as the new value is not *used* in the same transaction (it isn't). The `RENAME VALUE`
statements are guarded on label existence so the migration is idempotent and safe to
apply over a DB that was already partially hand-fixed.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'PO_SUBMITTED'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'VESSEL_APPROACHING'")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                       WHERE t.typname = 'notificationtype' AND e.enumlabel = 'ar_aging_alert')
            AND NOT EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                       WHERE t.typname = 'notificationtype' AND e.enumlabel = 'AR_AGING_ALERT')
            THEN
                ALTER TYPE notificationtype RENAME VALUE 'ar_aging_alert' TO 'AR_AGING_ALERT';
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                       WHERE t.typname = 'notificationtype' AND e.enumlabel = 'demurrage_warning')
            AND NOT EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                       WHERE t.typname = 'notificationtype' AND e.enumlabel = 'DEMURRAGE_WARNING')
            THEN
                ALTER TYPE notificationtype RENAME VALUE 'demurrage_warning' TO 'DEMURRAGE_WARNING';
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # PostgreSQL cannot drop enum values, so PO_SUBMITTED / VESSEL_APPROACHING
    # remain after downgrade. Restore the two renamed labels to their prior
    # (mis-cased) form so the chain is reversible to d3e4f5a6b7c8's state.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                       WHERE t.typname = 'notificationtype' AND e.enumlabel = 'AR_AGING_ALERT')
            AND NOT EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                       WHERE t.typname = 'notificationtype' AND e.enumlabel = 'ar_aging_alert')
            THEN
                ALTER TYPE notificationtype RENAME VALUE 'AR_AGING_ALERT' TO 'ar_aging_alert';
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                       WHERE t.typname = 'notificationtype' AND e.enumlabel = 'DEMURRAGE_WARNING')
            AND NOT EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                       WHERE t.typname = 'notificationtype' AND e.enumlabel = 'demurrage_warning')
            THEN
                ALTER TYPE notificationtype RENAME VALUE 'DEMURRAGE_WARNING' TO 'demurrage_warning';
            END IF;
        END$$;
        """
    )
