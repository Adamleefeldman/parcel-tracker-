"""p1.5: vessel_updates.created_by nullable for system writes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-30 00:00:00.000000

The VesselFinder polling worker (P1.5) writes VesselUpdate rows from a
background task with no acting user. Rather than seed a synthetic
"system" user (which would need ongoing maintenance and would muddy
audit semantics if anyone ever logged in as it), we make `created_by`
nullable. NULL `created_by` means "system-generated" — pair this with
a non-null `source` (e.g. "vesselfinder") to identify the writer.

User-initiated VesselUpdate rows continue to set `created_by` and the
route layer is unchanged (no NULL is ever written from a request path).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "vessel_updates",
        "created_by",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # Backfill any NULL rows with a placeholder before re-applying NOT NULL.
    # Production rollback should choose its own strategy (delete system rows,
    # or assign to a fallback user) — leaving the NOT NULL re-add only.
    # Operators that need to roll back must first resolve any NULLs by hand.
    op.alter_column(
        "vessel_updates",
        "created_by",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
