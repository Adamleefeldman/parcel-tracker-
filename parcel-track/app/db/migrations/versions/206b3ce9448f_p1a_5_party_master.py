"""p1a_5_party_master

Revision ID: 206b3ce9448f
Revises: 8944b3e39914
Create Date: 2026-07-08 17:15:22.661137

Data-Foundation Pillar 3 (spec §4). Adds the `parties` master (suppliers and
every non-customer counterparty) + child `party_bank_accounts`, and a nullable
`supplier_party_id` FK on `purchase_orders` (alongside the legacy free-text
`supplier_ref`). Seeds the single existing supplier "SCDB" and backfills every
existing PO to it. Both new tables get deny-all RLS inline (belt-and-braces).

NOT NULL tightening of `supplier_party_id` is deferred to Session 5 (`p1a_11`).
Broker/Company (customer-side) are deliberately untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "206b3ce9448f"
down_revision: str | None = "8944b3e39914"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── PartyType enum ───────────────────────────────────────────────────────
    party_type_enum = postgresql.ENUM(
        "supplier",
        "freight_forwarder",
        "haulier",
        "warehouse_operator",
        "customs_broker",
        name="partytype",
        create_type=False,
    )
    party_type_enum.create(op.get_bind(), checkfirst=True)

    # ── parties ──────────────────────────────────────────────────────────────
    op.create_table(
        "parties",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("party_type", party_type_enum, nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("default_currency_code", sa.String(length=3), nullable=True),
        sa.Column("default_payment_terms", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
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
            ["default_currency_code"],
            ["currencies.code"],
            name="parties_default_currency_code_fkey",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("party_type", "code", name="uq_parties_type_code"),
    )
    op.create_index("ix_parties_party_type", "parties", ["party_type"])
    op.execute("ALTER TABLE parties ENABLE ROW LEVEL SECURITY")

    # ── party_bank_accounts ──────────────────────────────────────────────────
    op.create_table(
        "party_bank_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("party_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("bank_name", sa.String(length=200), nullable=True),
        sa.Column("account_name", sa.String(length=200), nullable=True),
        sa.Column("iban", sa.String(length=40), nullable=True),
        sa.Column("swift_bic", sa.String(length=20), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            ["party_id"],
            ["parties.id"],
            name="party_bank_accounts_party_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="party_bank_accounts_currency_code_fkey",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_party_bank_accounts_party_id", "party_bank_accounts", ["party_id"])
    op.execute("ALTER TABLE party_bank_accounts ENABLE ROW LEVEL SECURITY")

    # ── purchase_orders.supplier_party_id (nullable, backfilled) ─────────────
    op.add_column("purchase_orders", sa.Column("supplier_party_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_purchase_orders_supplier_party_id",
        "purchase_orders",
        ["supplier_party_id"],
    )
    op.create_foreign_key(
        "purchase_orders_supplier_party_id_fkey",
        "purchase_orders",
        "parties",
        ["supplier_party_id"],
        ["id"],
    )

    # ── Seed the single existing supplier + backfill existing POs ────────────
    op.execute(
        """
        INSERT INTO parties
            (id, party_type, code, name, country, default_currency_code, is_active)
        VALUES
            (gen_random_uuid(), 'supplier', 'SCDB', 'SCDB', 'Morocco', 'USD', true)
        ON CONFLICT (party_type, code) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE purchase_orders
        SET supplier_party_id =
            (SELECT id FROM parties WHERE party_type = 'supplier' AND code = 'SCDB')
        WHERE supplier_party_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "purchase_orders_supplier_party_id_fkey", "purchase_orders", type_="foreignkey"
    )
    op.drop_index("ix_purchase_orders_supplier_party_id", table_name="purchase_orders")
    op.drop_column("purchase_orders", "supplier_party_id")

    op.drop_table("party_bank_accounts")
    op.drop_table("parties")

    party_type_enum = postgresql.ENUM(name="partytype", create_type=False)
    party_type_enum.drop(op.get_bind(), checkfirst=True)
