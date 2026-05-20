"""p1.1: multi-leg ShipmentLeg

Revision ID: f1a2b3c4d5e6
Revises: a7b8c9d0e1f2
Create Date: 2026-05-20 12:00:00.000000

Real Maersk routes transship at Algeciras with a distinct vessel and voyage
per leg (Casablanca→Algeciras, then Algeciras→London Gateway). The 1:1
`Vessel`↔`BillOfLading` model can only hold one of those legs. This migration
adds `shipment_legs` — an ordered, per-booking record of the full route.

This is additive: `Vessel` is untouched and stays the polling + lifecycle
driver for the final leg.

Table created:
  shipment_legs (id, booking_id FK, leg_index, vessel_name, imo_number,
                 voyage_number, shipping_line, port_from, port_to,
                 etd, atd, eta, ata, created_at, updated_at)

`leg_index` is 1-based, unique within a booking (uq constraint) and CHECK
`>= 1`. RLS is enabled to match the deny-all default from migration
5ab45b2e1574.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipment_legs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leg_index", sa.Integer(), nullable=False),
        sa.Column("vessel_name", sa.String(length=255), nullable=False),
        sa.Column("imo_number", sa.String(length=20), nullable=True),
        sa.Column("voyage_number", sa.String(length=50), nullable=True),
        sa.Column("shipping_line", sa.String(length=255), nullable=False),
        sa.Column("port_from", sa.String(length=100), nullable=False),
        sa.Column("port_to", sa.String(length=100), nullable=False),
        sa.Column("etd", sa.Date(), nullable=True),
        sa.Column("atd", sa.Date(), nullable=True),
        sa.Column("eta", sa.Date(), nullable=True),
        sa.Column("ata", sa.Date(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("booking_id", "leg_index", name="uq_shipment_legs_booking_leg_index"),
        sa.CheckConstraint("leg_index >= 1", name="ck_shipment_legs_leg_index_positive"),
    )
    op.create_index("ix_shipment_legs_booking_id", "shipment_legs", ["booking_id"])

    # RLS: deny-all by default, consistent with migration 5ab45b2e1574.
    op.execute("ALTER TABLE shipment_legs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE shipment_legs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_shipment_legs_booking_id", table_name="shipment_legs")
    op.drop_table("shipment_legs")
