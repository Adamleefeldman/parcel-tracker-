"""p1a.3: money USD-capture columns

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-07-03 09:10:00.000000

Data-Foundation Pillar 1c (spec §2.4). Adds the "locked rate" capture pair to
every money-holding row: `fx_rate_to_usd` (the native->USD rate frozen at write
time) and `amount_usd` (the stored USD-equivalent). Both nullable — historical
rows, and rows written while the FX feed is dormant, simply stay NULL (a NULL
`amount_usd` is the "not yet converted" signal). No backfill; no NOT NULL
follow-up — these columns are legitimately nullable forever.

Tables: purchase_orders, invoices, supplier_payments, customer_payments, containers.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("purchase_orders", "invoices", "supplier_payments", "customer_payments", "containers")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("fx_rate_to_usd", sa.Numeric(18, 8), nullable=True))
        op.add_column(table, sa.Column("amount_usd", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "amount_usd")
        op.drop_column(table, "fx_rate_to_usd")
