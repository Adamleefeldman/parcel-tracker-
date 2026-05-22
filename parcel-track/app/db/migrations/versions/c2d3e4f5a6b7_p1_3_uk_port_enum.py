"""p1.3: UK port-of-discharge enum + PortTemplate

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-22 10:10:00.000000

UK discharge ports each have distinct free-day defaults and fee structures.
This migration:
  - creates the `ukport` enum type;
  - creates the `port_templates` lookup table (one row per port) with RLS;
  - converts `bills_of_lading.port_of_discharge` from free-text String(100)
    to the `ukport` enum, mapping known port names case-insensitively and
    defaulting anything unrecognised to 'other'.

`vessels.port_of_discharge` is intentionally left as String — it feeds the
UNLOCODE→coordinate lookup in the VesselFinder poller.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UK_PORTS = ("felixstowe", "london_gateway", "tilbury", "southampton", "liverpool", "other")


def upgrade() -> None:
    # ── ukport enum type ──────────────────────────────────────────────────────
    ukport = postgresql.ENUM(*_UK_PORTS, name="ukport", create_type=False)
    ukport.create(op.get_bind(), checkfirst=True)

    # ── port_templates ────────────────────────────────────────────────────────
    op.create_table(
        "port_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("port", ukport, nullable=False),
        sa.Column("free_days_detention", sa.Integer(), nullable=False),
        sa.Column("free_days_demurrage", sa.Integer(), nullable=False),
        sa.Column("detention_rate_gbp_after", sa.Numeric(12, 2), nullable=True),
        sa.Column("demurrage_rate_gbp_after", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("port", name="uq_port_templates_port"),
        sa.CheckConstraint("free_days_detention >= 0", name="ck_port_templates_detention_days"),
        sa.CheckConstraint("free_days_demurrage >= 0", name="ck_port_templates_demurrage_days"),
        sa.CheckConstraint(
            "detention_rate_gbp_after IS NULL OR detention_rate_gbp_after >= 0",
            name="ck_port_templates_detention_rate",
        ),
        sa.CheckConstraint(
            "demurrage_rate_gbp_after IS NULL OR demurrage_rate_gbp_after >= 0",
            name="ck_port_templates_demurrage_rate",
        ),
    )
    op.execute("ALTER TABLE port_templates ENABLE ROW LEVEL SECURITY")

    # ── convert bills_of_lading.port_of_discharge String → ukport ─────────────
    op.execute(
        """
        ALTER TABLE bills_of_lading
        ALTER COLUMN port_of_discharge TYPE ukport
        USING (
            CASE lower(trim(port_of_discharge))
                WHEN 'felixstowe' THEN 'felixstowe'
                WHEN 'london gateway' THEN 'london_gateway'
                WHEN 'london_gateway' THEN 'london_gateway'
                WHEN 'tilbury' THEN 'tilbury'
                WHEN 'southampton' THEN 'southampton'
                WHEN 'liverpool' THEN 'liverpool'
                ELSE 'other'
            END::ukport
        )
        """
    )


def downgrade() -> None:
    # Revert the BL column to free text (the enum value's string form).
    op.execute(
        "ALTER TABLE bills_of_lading "
        "ALTER COLUMN port_of_discharge TYPE varchar(100) "
        "USING port_of_discharge::text"
    )
    op.execute("ALTER TABLE port_templates DISABLE ROW LEVEL SECURITY")
    op.drop_table("port_templates")
    postgresql.ENUM(*_UK_PORTS, name="ukport", create_type=False).drop(
        op.get_bind(), checkfirst=True
    )
