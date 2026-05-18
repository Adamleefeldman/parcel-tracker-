"""p0.4: container lifecycle_status + vessel.ata + dispute fields

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-17 17:00:00.000000

Adds the end-to-end ContainerLifecycleStatus enum + column so dashboards
and the booking-level COMPLETE precondition can answer "is this container
done?" without joining four tables. Also adds:

  vessels.ata                   — actual arrival date (single-leg, P0.4 only)
  containers.dispute_reason     — free text when DISPUTED side-state set
  containers.disputed_at        — timestamp marking the dispute open

The new enum is `containerlifecyclestatus`. All existing containers
default to ORDERED — operations can run a one-shot recompute job after
deployment to backfill the rest from inputs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Enum ─────────────────────────────────────────────────────────────────
    lifecycle_enum = postgresql.ENUM(
        "ordered",
        "at_sea",
        "arrived",
        "import_cleared",
        "delivered",
        "invoiced",
        "paid",
        "banked",
        "closed",
        "disputed",
        name="containerlifecyclestatus",
        create_type=False,
    )
    lifecycle_enum.create(op.get_bind(), checkfirst=True)

    # ── vessels.ata ──────────────────────────────────────────────────────────
    op.add_column("vessels", sa.Column("ata", sa.Date(), nullable=True))

    # ── containers: lifecycle_status + dispute fields ────────────────────────
    op.add_column(
        "containers",
        sa.Column(
            "lifecycle_status",
            lifecycle_enum,
            server_default="ordered",
            nullable=False,
        ),
    )
    op.add_column("containers", sa.Column("dispute_reason", sa.Text(), nullable=True))
    op.add_column("containers", sa.Column("disputed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("containers", "disputed_at")
    op.drop_column("containers", "dispute_reason")
    op.drop_column("containers", "lifecycle_status")
    op.drop_column("vessels", "ata")

    lifecycle_enum = postgresql.ENUM(name="containerlifecyclestatus", create_type=False)
    lifecycle_enum.drop(op.get_bind(), checkfirst=True)
