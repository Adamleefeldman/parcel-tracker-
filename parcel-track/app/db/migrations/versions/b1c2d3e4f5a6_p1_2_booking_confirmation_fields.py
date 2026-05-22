"""p1.2: booking-confirmation fields

Revision ID: b1c2d3e4f5a6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-22 10:00:00.000000

The carrier's Booking Confirmation PDF carries free-day clocks, per-day rates
after free time, gate-in / empty-container windows, the discharge terminal,
and the service mode. These are added to `bookings` as 9 nullable columns —
a booking is created (DRAFT) before the confirmation arrives, so every field
is nullable with no default.

CHECK constraints keep the two rate columns non-negative where set.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bookings", sa.Column("gate_in_cutoff", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("empty_pickup_release", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("empty_return_deadline", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("bookings", sa.Column("free_days_detention", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("free_days_demurrage", sa.Integer(), nullable=True))
    op.add_column(
        "bookings", sa.Column("detention_rate_gbp_after", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("demurrage_rate_gbp_after", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("port_of_discharge_terminal", sa.String(length=255), nullable=True)
    )
    op.add_column("bookings", sa.Column("service_mode", sa.String(length=20), nullable=True))

    op.create_check_constraint(
        "ck_bookings_detention_rate_non_negative",
        "bookings",
        "detention_rate_gbp_after IS NULL OR detention_rate_gbp_after >= 0",
    )
    op.create_check_constraint(
        "ck_bookings_demurrage_rate_non_negative",
        "bookings",
        "demurrage_rate_gbp_after IS NULL OR demurrage_rate_gbp_after >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bookings_demurrage_rate_non_negative", "bookings", type_="check")
    op.drop_constraint("ck_bookings_detention_rate_non_negative", "bookings", type_="check")
    op.drop_column("bookings", "service_mode")
    op.drop_column("bookings", "port_of_discharge_terminal")
    op.drop_column("bookings", "demurrage_rate_gbp_after")
    op.drop_column("bookings", "detention_rate_gbp_after")
    op.drop_column("bookings", "free_days_demurrage")
    op.drop_column("bookings", "free_days_detention")
    op.drop_column("bookings", "empty_return_deadline")
    op.drop_column("bookings", "empty_pickup_release")
    op.drop_column("bookings", "gate_in_cutoff")
