"""p0.5: delivery-point broker + end_company + delivery_type fields

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-17 17:30:00.000000

Adds the customer-side parties (broker + end_company) and delivery-type
metadata to delivery_points. Mirrors what already lives on containers:
the broker is the POC arranging the drop, the end_company is the buying
firm, and delivery_type captures the Direct vs Via-Warehouse pattern.

Backward compatibility: the legacy ``customer_user_id`` column stays
(nullable) so older clients writing the field still work.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    delivery_type_enum = postgresql.ENUM(
        "direct", "via_warehouse", name="deliverytype", create_type=False
    )

    op.add_column(
        "delivery_points",
        sa.Column("broker_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "delivery_points",
        sa.Column("end_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "delivery_points",
        sa.Column("delivery_type", delivery_type_enum, nullable=True),
    )
    op.add_column(
        "delivery_points",
        sa.Column("warehouse_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "delivery_points",
        sa.Column(
            "rebundled_at_warehouse",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    op.create_index("ix_delivery_points_broker_id", "delivery_points", ["broker_id"])
    op.create_index("ix_delivery_points_end_company_id", "delivery_points", ["end_company_id"])

    op.create_foreign_key(
        "delivery_points_broker_id_fkey",
        "delivery_points",
        "brokers",
        ["broker_id"],
        ["id"],
    )
    op.create_foreign_key(
        "delivery_points_end_company_id_fkey",
        "delivery_points",
        "companies",
        ["end_company_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("delivery_points_end_company_id_fkey", "delivery_points", type_="foreignkey")
    op.drop_constraint("delivery_points_broker_id_fkey", "delivery_points", type_="foreignkey")
    op.drop_index("ix_delivery_points_end_company_id", table_name="delivery_points")
    op.drop_index("ix_delivery_points_broker_id", table_name="delivery_points")

    op.drop_column("delivery_points", "rebundled_at_warehouse")
    op.drop_column("delivery_points", "warehouse_name")
    op.drop_column("delivery_points", "delivery_type")
    op.drop_column("delivery_points", "end_company_id")
    op.drop_column("delivery_points", "broker_id")
