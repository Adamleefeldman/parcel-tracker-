"""p1a.2: fx_rates append-only rate history

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-07-03 09:00:00.000000

Data-Foundation Pillar 1b (spec §2.3). Append-only history of observed FX rates
(base always USD). The ExchangeRate-API poller inserts one snapshot per provider
update; `FxService.rate_to_usd` reads the latest row at/under a given time so a
historical transaction can freeze the rate that was live when it was written.

`base_code` / `quote_code` FK the `currencies` table (from p1a.1). RLS deny-all
is enabled inline, matching the additive `shipment_legs` migration (f1a2b3c4d5e6)
and the 5ab45b2e1574 default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b0c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fx_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_code", sa.String(length=3), nullable=False),
        sa.Column("quote_code", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source", sa.String(length=40), server_default="exchangerate_api", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["base_code"], ["currencies.code"]),
        sa.ForeignKeyConstraint(["quote_code"], ["currencies.code"]),
        sa.CheckConstraint("rate > 0", name="ck_fx_rates_rate_positive"),
    )
    op.create_index("ix_fx_rates_quote_asof", "fx_rates", ["quote_code", "as_of"])
    op.create_index("ix_fx_rates_as_of", "fx_rates", ["as_of"])
    op.execute("ALTER TABLE fx_rates ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE fx_rates DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_fx_rates_as_of", table_name="fx_rates")
    op.drop_index("ix_fx_rates_quote_asof", table_name="fx_rates")
    op.drop_table("fx_rates")
