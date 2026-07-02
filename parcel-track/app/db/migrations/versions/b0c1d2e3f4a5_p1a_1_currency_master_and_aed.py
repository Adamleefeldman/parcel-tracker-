"""p1a.1: currency master table + AED enum value

Revision ID: b0c1d2e3f4a5
Revises: a0b1c2d3e4f5
Create Date: 2026-07-02 09:05:00.000000

Data-Foundation Pillar 1 (spec §2.2). Adds:

  * 'AED' to the existing `currency` enum (was USD/GBP/EUR/MAD).
  * `currencies` reference table (config-over-code) + an idempotent seed.

The legacy `Currency` enum columns are intentionally left as-is; only NEW
currency-referencing columns will FK to `currencies.code` (spec §2.2 —
"don't half-migrate"). RLS deny-all is enabled inline, matching the additive
`shipment_legs` migration (f1a2b3c4d5e6) and the 5ab45b2e1574 default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b0c1d2e3f4a5"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add AED to the existing `currency` enum. Mirrors a6b7c8d9e0f1; PG12+
    #    transaction-safe because AED is not *used* in this migration
    #    (currencies.code below is a plain String, not the enum type).
    op.execute("ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AED'")

    # 2. currencies reference table.
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=True),
        sa.Column("minor_units", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column("is_base", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.PrimaryKeyConstraint("code"),
    )

    # 3. Idempotent seed. USD is the reporting base (exactly one is_base=true).
    op.execute(
        """
        INSERT INTO currencies (code, name, symbol, minor_units, is_base, is_active) VALUES
            ('USD', 'US Dollar', '$', 2, true, true),
            ('GBP', 'Pound Sterling', '£', 2, false, true),
            ('EUR', 'Euro', '€', 2, false, true),
            ('MAD', 'Moroccan Dirham', 'DH', 2, false, true),
            ('AED', 'UAE Dirham', 'AED', 2, false, true)
        ON CONFLICT (code) DO NOTHING
        """
    )

    # 4. RLS deny-all (consistent with 5ab45b2e1574 / shipment_legs).
    op.execute("ALTER TABLE currencies ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE currencies DISABLE ROW LEVEL SECURITY")
    op.drop_table("currencies")
    # PostgreSQL cannot DROP a value from an enum type, so 'AED' remains on the
    # `currency` type after downgrade. Harmless (it is simply unused).
