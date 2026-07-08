"""p1a.4: legal entities (multi-entity tagging)

Revision ID: 8944b3e39914
Revises: d1e2f3a4b5c6
Create Date: 2026-07-08 15:41:17.953136

Data-Foundation Pillar 2 (spec §3). Introduces the `legal_entities` master table
(one seeded default: WT Trading LLC / The FMCG Hub) and tags every money/shipment
row with an owning entity via a nullable `legal_entity_id` FK, backfilled to the
default. The tag stays nullable here; the NOT NULL tightening is deferred to the
Session-5 sweep (`p1a_11`) once every row is confirmed backfilled.

RLS is enabled inline on `legal_entities` (belt-and-braces per spec §0.4) so it
can never be read via the Supabase anon key. The six tagged tables already carry
RLS from `5ab45b2e1574`.

Tables tagged: purchase_orders, invoices, supplier_payments, customer_payments,
bookings, containers.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8944b3e39914"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The transaction tables that gain the multi-entity tag.
_TAG_TABLES = (
    "purchase_orders",
    "invoices",
    "supplier_payments",
    "customer_payments",
    "bookings",
    "containers",
)


def upgrade() -> None:
    op.create_table(
        "legal_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction", sa.String(length=80), nullable=True),
        sa.Column("base_currency_code", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["base_currency_code"],
            ["currencies.code"],
            name="legal_entities_base_currency_code_fkey",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="legal_entities_code_key"),
    )
    op.execute("ALTER TABLE legal_entities ENABLE ROW LEVEL SECURITY")

    # Seed the single default entity (idempotent). gen_random_uuid() is core in
    # PG13+ (already used by c3d4e5f6a7b8), so no extension is required.
    op.execute(
        """
        INSERT INTO legal_entities
            (id, code, legal_name, display_name, jurisdiction, base_currency_code,
             is_default, is_active)
        VALUES
            (gen_random_uuid(), 'FMCG_HUB', 'WT Trading LLC', 'The FMCG Hub',
             'UAE Free Zone', 'USD', true, true)
        ON CONFLICT (code) DO NOTHING
        """
    )

    # Tag each transaction table (nullable + indexed FK), then backfill existing
    # rows to the default entity.
    for table in _TAG_TABLES:
        op.add_column(
            table, sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        op.create_index(f"ix_{table}_legal_entity_id", table, ["legal_entity_id"])
        op.create_foreign_key(
            f"{table}_legal_entity_id_fkey",
            table,
            "legal_entities",
            ["legal_entity_id"],
            ["id"],
        )
        op.execute(
            f"UPDATE {table} SET legal_entity_id = "  # noqa: S608 (table from internal constant)
            "(SELECT id FROM legal_entities WHERE is_default) "
            "WHERE legal_entity_id IS NULL"
        )


def downgrade() -> None:
    for table in reversed(_TAG_TABLES):
        op.drop_constraint(f"{table}_legal_entity_id_fkey", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_legal_entity_id", table_name=table)
        op.drop_column(table, "legal_entity_id")
    op.execute("ALTER TABLE legal_entities DISABLE ROW LEVEL SECURITY")
    op.drop_table("legal_entities")
