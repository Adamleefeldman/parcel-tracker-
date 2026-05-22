"""p1.4/p1.5: notification types for A/R aging + demurrage

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-22 10:20:00.000000

Adds two values to the `notificationtype` enum used by the A/R aging task
(P1.4) and the demurrage countdown task (P1.5).

PostgreSQL 12+ permits `ALTER TYPE ... ADD VALUE` inside a transaction as long
as the new value is not *used* in the same transaction — which it isn't here.

`downgrade` is a no-op: PostgreSQL has no `ALTER TYPE ... DROP VALUE`. Removing
an enum value would require recreating the type and rewriting every dependent
column — not worth it for a reversible-migration formality.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ar_aging_alert'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'demurrage_warning'")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values — intentionally a no-op.
    pass
