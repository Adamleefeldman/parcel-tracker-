"""p2.1: container dispute acknowledgement fields

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-05-22 14:00:00.000000

Adds the two columns that let an admin mark an open dispute as acknowledged
so the parent booking can reach `COMPLETE`. The dispute itself
(`dispute_reason` + `disputed_at`) is preserved — these new columns are
markers, not erasers.

  containers.dispute_acknowledged_at  TIMESTAMPTZ nullable
  containers.dispute_acknowledged_by  UUID FK users(id) nullable
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "containers",
        sa.Column("dispute_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "containers",
        sa.Column("dispute_acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "containers_dispute_acknowledged_by_fkey",
        "containers",
        "users",
        ["dispute_acknowledged_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("containers_dispute_acknowledged_by_fkey", "containers", type_="foreignkey")
    op.drop_column("containers", "dispute_acknowledged_by")
    op.drop_column("containers", "dispute_acknowledged_at")
