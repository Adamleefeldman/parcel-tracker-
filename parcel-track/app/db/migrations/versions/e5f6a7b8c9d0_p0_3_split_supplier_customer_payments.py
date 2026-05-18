"""p0.3: split Payment into SupplierPayment (per-Invoice) + CustomerPayment

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-17 16:30:00.000000

Splits the bidirectional Payment table:

  payments (P0.1) — booking-scoped USD outflows. Now becomes
  supplier_payments — invoice-scoped USD outflows (one Invoice has N
  SupplierPayments). The column ``booking_id`` is replaced with
  ``invoice_id``; the existing rows are backfilled by walking the
  many-to-many junction (BookingPurchaseOrder → PurchaseOrder → Invoice).
  Each old payment maps to the *first* Invoice attached to its booking;
  this works because dev/test data has at most one Invoice per Booking
  and there are no production rows.

Also adds a fresh table:

  customer_payments — container-scoped GBP inflows from UK customers.
  Carries the cash/transfer method, variance, expense splits (courier +
  bank charge), banked total, sender/receiver bank, multi-tranche index,
  and the outbound-invoice-batch reference string.

The Postgres enum ``paymenttype`` is left intact — it now stands for the
SupplierPaymentType values (FULL / PARTIAL / DEPOSIT). The new
``customerpaymentmethod`` enum is created here.

RLS is enabled on customer_payments to match the deny-all default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Rename the table ───────────────────────────────────────────────────
    op.rename_table("payments", "supplier_payments")

    # ── 2. Add invoice_id (nullable), backfill, then make it NOT NULL ────────
    op.add_column(
        "supplier_payments",
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Backfill: walk booking_id → BookingPurchaseOrder → PurchaseOrder →
    # Invoice. With one Invoice per Booking in dev data, this picks that
    # single Invoice. For genuinely multi-invoice bookings (no production
    # data exists yet) the resolution is "first invoice on the booking";
    # operators with real multi-invoice data must reconcile by hand.
    op.execute(
        """
        UPDATE supplier_payments sp
           SET invoice_id = sub.invoice_id
          FROM (
            SELECT DISTINCT ON (bpo.booking_id) bpo.booking_id, i.id AS invoice_id
              FROM booking_purchase_orders bpo
              JOIN purchase_orders po ON po.id = bpo.purchase_order_id
              JOIN invoices i ON i.purchase_order_id = po.id
             ORDER BY bpo.booking_id, i.created_at
          ) sub
         WHERE sub.booking_id = sp.booking_id
        """
    )

    op.alter_column("supplier_payments", "invoice_id", nullable=False)
    op.create_foreign_key(
        "supplier_payments_invoice_id_fkey",
        "supplier_payments",
        "invoices",
        ["invoice_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_supplier_payments_invoice_id", "supplier_payments", ["invoice_id"])

    # ── 3. Drop the old booking_id linkage ───────────────────────────────────
    op.drop_constraint("payments_booking_id_fkey", "supplier_payments", type_="foreignkey")
    op.execute("ALTER INDEX ix_payments_booking_id RENAME TO ix_supplier_payments_booking_id")
    op.drop_index("ix_supplier_payments_booking_id", table_name="supplier_payments")
    op.drop_column("supplier_payments", "booking_id")

    # Rename the CHECK constraint to match the new table name.
    op.execute(
        "ALTER TABLE supplier_payments RENAME CONSTRAINT ck_payments_amount_positive"
        " TO ck_supplier_payments_amount_positive"
    )

    # ── 4. CustomerPaymentMethod enum + customer_payments table ──────────────
    customer_method_enum = postgresql.ENUM(
        "cash", "transfer", name="customerpaymentmethod", create_type=False
    )
    customer_method_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "customer_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("container_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("method", customer_method_enum, nullable=False),
        sa.Column("amount_received", sa.Numeric(14, 2), nullable=False),
        sa.Column("variance", sa.Numeric(12, 2), nullable=True),
        sa.Column("expense_courier", sa.Numeric(10, 2), nullable=True),
        sa.Column("expense_bank_charge", sa.Numeric(10, 2), nullable=True),
        sa.Column("banked_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("sender_bank", sa.String(200), nullable=True),
        sa.Column("receiver_bank", sa.String(200), nullable=True),
        sa.Column("tranche_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("customer_invoice_ref", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["container_id"], ["containers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "amount_received > 0", name="ck_customer_payments_amount_received_positive"
        ),
        sa.CheckConstraint(
            "expense_courier IS NULL OR expense_courier >= 0",
            name="ck_customer_payments_expense_courier_non_negative",
        ),
        sa.CheckConstraint(
            "expense_bank_charge IS NULL OR expense_bank_charge >= 0",
            name="ck_customer_payments_expense_bank_charge_non_negative",
        ),
        sa.CheckConstraint(
            "tranche_index >= 1", name="ck_customer_payments_tranche_index_positive"
        ),
    )
    op.create_index("ix_customer_payments_container_id", "customer_payments", ["container_id"])

    op.execute("ALTER TABLE customer_payments ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE customer_payments DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_customer_payments_container_id", table_name="customer_payments")
    op.drop_table("customer_payments")

    customer_method_enum = postgresql.ENUM(
        "cash", "transfer", name="customerpaymentmethod", create_type=False
    )
    customer_method_enum.drop(op.get_bind(), checkfirst=True)

    # Restore booking_id column + FK on supplier_payments, backfill from
    # the junction (first booking the invoice's PO is linked to), then
    # rename the table back to `payments`.
    op.add_column(
        "supplier_payments",
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE supplier_payments sp
           SET booking_id = sub.booking_id
          FROM (
            SELECT DISTINCT ON (i.id) i.id AS invoice_id, bpo.booking_id
              FROM invoices i
              JOIN booking_purchase_orders bpo ON bpo.purchase_order_id = i.purchase_order_id
             ORDER BY i.id, bpo.added_at
          ) sub
         WHERE sub.invoice_id = sp.invoice_id
        """
    )
    op.alter_column("supplier_payments", "booking_id", nullable=False)
    op.create_foreign_key(
        "payments_booking_id_fkey",
        "supplier_payments",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_payments_booking_id", "supplier_payments", ["booking_id"])

    op.drop_index("ix_supplier_payments_invoice_id", table_name="supplier_payments")
    op.drop_constraint("supplier_payments_invoice_id_fkey", "supplier_payments", type_="foreignkey")
    op.drop_column("supplier_payments", "invoice_id")

    op.execute(
        "ALTER TABLE supplier_payments RENAME CONSTRAINT ck_supplier_payments_amount_positive"
        " TO ck_payments_amount_positive"
    )

    op.rename_table("supplier_payments", "payments")
