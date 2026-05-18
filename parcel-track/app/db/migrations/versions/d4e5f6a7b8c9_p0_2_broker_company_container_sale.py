"""p0.2: Broker + Company + container sale-side fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-17 16:00:00.000000

Container is the operational unit of the business. Each container has its
own sale price, broker (POC arranging the sale, e.g. ZAF / IFFY), end
company (the receiving firm, e.g. Chesertons / Surplus / Aryana), and
delivery type (Direct vs Via Warehouse). This migration adds the two
new lookup tables and the per-container fields.

Tables created:
  brokers     (id, code unique, name, phone)
  companies   (id, legal_name unique, aliases JSON, registration_no,
               vat_no, default_address)

Columns added to containers:
  delivery_type           SAEnum(deliverytype)  nullable
  broker_id               UUID FK brokers(id)   nullable
  end_company_id          UUID FK companies(id) nullable
  sale_price_per_tray     Numeric(10,2)         nullable
  sale_price_per_pallet   Numeric(12,2)         nullable
  sale_price_total        Numeric(14,2)         nullable
  sale_currency           SAEnum(currency)      NOT NULL default 'GBP'

CHECK constraints enforce sale_price_* >= 0 where set. Both new tables
get RLS enabled to match the deny-all default established in migration
5ab45b2e1574.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── New enum: deliverytype ────────────────────────────────────────────────
    delivery_type_enum = postgresql.ENUM(
        "direct", "via_warehouse", name="deliverytype", create_type=False
    )
    delivery_type_enum.create(op.get_bind(), checkfirst=True)

    # ── brokers ───────────────────────────────────────────────────────────────
    op.create_table(
        "brokers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
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
        sa.UniqueConstraint("code", name="brokers_code_key"),
    )

    # ── companies ─────────────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("registration_no", sa.String(length=50), nullable=True),
        sa.Column("vat_no", sa.String(length=50), nullable=True),
        sa.Column("default_address", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("legal_name", name="companies_legal_name_key"),
    )

    # ── containers: new sale-side columns ─────────────────────────────────────
    op.add_column(
        "containers",
        sa.Column("delivery_type", delivery_type_enum, nullable=True),
    )
    op.add_column(
        "containers",
        sa.Column("broker_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "containers",
        sa.Column("end_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "containers",
        sa.Column("sale_price_per_tray", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "containers",
        sa.Column("sale_price_per_pallet", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "containers",
        sa.Column("sale_price_total", sa.Numeric(14, 2), nullable=True),
    )
    # sale_currency reuses the existing `currency` enum; default 'GBP' for any
    # existing rows so the NOT NULL add is safe.
    op.add_column(
        "containers",
        sa.Column(
            "sale_currency",
            postgresql.ENUM(name="currency", create_type=False),
            server_default="GBP",
            nullable=False,
        ),
    )

    op.create_index("ix_containers_broker_id", "containers", ["broker_id"])
    op.create_index("ix_containers_end_company_id", "containers", ["end_company_id"])

    op.create_foreign_key(
        "containers_broker_id_fkey",
        "containers",
        "brokers",
        ["broker_id"],
        ["id"],
    )
    op.create_foreign_key(
        "containers_end_company_id_fkey",
        "containers",
        "companies",
        ["end_company_id"],
        ["id"],
    )

    op.create_check_constraint(
        "ck_containers_sale_price_per_tray_non_negative",
        "containers",
        "sale_price_per_tray IS NULL OR sale_price_per_tray >= 0",
    )
    op.create_check_constraint(
        "ck_containers_sale_price_per_pallet_non_negative",
        "containers",
        "sale_price_per_pallet IS NULL OR sale_price_per_pallet >= 0",
    )
    op.create_check_constraint(
        "ck_containers_sale_price_total_non_negative",
        "containers",
        "sale_price_total IS NULL OR sale_price_total >= 0",
    )

    # ── RLS on the two new tables ────────────────────────────────────────────
    op.execute("ALTER TABLE brokers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE brokers DISABLE ROW LEVEL SECURITY")

    op.drop_constraint("ck_containers_sale_price_total_non_negative", "containers", type_="check")
    op.drop_constraint(
        "ck_containers_sale_price_per_pallet_non_negative", "containers", type_="check"
    )
    op.drop_constraint(
        "ck_containers_sale_price_per_tray_non_negative", "containers", type_="check"
    )

    op.drop_constraint("containers_end_company_id_fkey", "containers", type_="foreignkey")
    op.drop_constraint("containers_broker_id_fkey", "containers", type_="foreignkey")
    op.drop_index("ix_containers_end_company_id", table_name="containers")
    op.drop_index("ix_containers_broker_id", table_name="containers")

    op.drop_column("containers", "sale_currency")
    op.drop_column("containers", "sale_price_total")
    op.drop_column("containers", "sale_price_per_pallet")
    op.drop_column("containers", "sale_price_per_tray")
    op.drop_column("containers", "end_company_id")
    op.drop_column("containers", "broker_id")
    op.drop_column("containers", "delivery_type")

    op.drop_table("companies")
    op.drop_table("brokers")

    delivery_type_enum = postgresql.ENUM(
        "direct", "via_warehouse", name="deliverytype", create_type=False
    )
    delivery_type_enum.drop(op.get_bind(), checkfirst=True)
