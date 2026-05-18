"""p0.1: rename Shipment → Booking; many-to-many PO↔Booking; Invoice→PO

Revision ID: c3d4e5f6a7b8
Revises: 5ab45b2e1574
Create Date: 2026-05-15 12:30:00.000000

Why
---
The previous schema assumed `Shipment ↔ PurchaseOrder ↔ BillOfLading` was
strictly 1:1:1. Real data shows one shipping-line booking can aggregate
multiple POs (e.g. DP World booking 2601008 covers PO-2026-04 + PO-2026-05).
The operational unit is the Booking — the carrier commitment — and the
container is what's actually being moved. This migration:

  1. Renames the `shipments` table → `bookings` (and `shipment_users` →
     `booking_users`) and adds a nullable `bookings.booking_number` for
     the carrier reference (e.g. Maersk 265232434).
  2. Renames every `<table>.shipment_id` column → `booking_id` on
     bills_of_lading, payments, clearing_docs, delivery_points,
     audit_logs, notifications, invite_tokens. Foreign keys are
     re-pointed at `bookings(id)`.
  3. Drops `purchase_orders.shipment_id` outright and creates a
     `booking_purchase_orders` junction (booking_id, purchase_order_id,
     unique pair) so a Booking can carry many POs and (in principle) a
     PO can be split across Bookings. Existing PO↔Shipment links are
     backfilled into the junction before the column is dropped.
  4. Moves `invoices.shipment_id` to `invoices.purchase_order_id` — each
     PurchaseOrder has exactly one supplier Commercial Invoice. Existing
     rows are rewired via the old 1:1 PO↔Shipment relationship.
  5. Renames the `ix_audit_logs_shipment_time` index to
     `ix_audit_logs_booking_time` to match the new column.

RLS is preserved by `ALTER TABLE … RENAME` (Postgres carries the per-table
RLS state through the rename). The new junction table has RLS enabled at
the bottom of the migration to match the deny-all default.

The downgrade undoes the schema shape but does NOT promise to round-trip
the data (multi-PO bookings introduced after upgrade have no place in the
old 1:1 model — those rows would have to be reconciled by hand).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "5ab45b2e1574"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Rename the top-level tables ────────────────────────────────────────
    op.rename_table("shipments", "bookings")
    op.rename_table("shipment_users", "booking_users")

    # bookings: add the shipping-line booking reference (nullable for back-
    # compat with rows created before this column existed).
    op.add_column(
        "bookings",
        sa.Column("booking_number", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_bookings_booking_number",
        "bookings",
        ["booking_number"],
        unique=True,
    )

    # ── 2. Rename shipment_id → booking_id on every child table ───────────────
    # Each column is renamed; the existing FK is dropped and recreated against
    # the new `bookings(id)` parent so the constraint name stays sensible.

    # booking_users
    op.alter_column("booking_users", "shipment_id", new_column_name="booking_id")
    op.drop_constraint("shipment_users_shipment_id_fkey", "booking_users", type_="foreignkey")
    op.create_foreign_key(
        "booking_users_booking_id_fkey",
        "booking_users",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("shipment_users_shipment_id_user_id_key", "booking_users", type_="unique")
    op.create_unique_constraint(
        "booking_users_booking_id_user_id_key",
        "booking_users",
        ["booking_id", "user_id"],
    )

    # invite_tokens.shipment_id → booking_id
    op.alter_column("invite_tokens", "shipment_id", new_column_name="booking_id")
    op.drop_constraint("invite_tokens_shipment_id_fkey", "invite_tokens", type_="foreignkey")
    op.create_foreign_key(
        "invite_tokens_booking_id_fkey",
        "invite_tokens",
        "bookings",
        ["booking_id"],
        ["id"],
    )

    # bills_of_lading
    op.alter_column("bills_of_lading", "shipment_id", new_column_name="booking_id")
    op.drop_constraint("bills_of_lading_shipment_id_fkey", "bills_of_lading", type_="foreignkey")
    op.create_foreign_key(
        "bills_of_lading_booking_id_fkey",
        "bills_of_lading",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("bills_of_lading_shipment_id_key", "bills_of_lading", type_="unique")
    op.create_unique_constraint("bills_of_lading_booking_id_key", "bills_of_lading", ["booking_id"])

    # payments
    op.alter_column("payments", "shipment_id", new_column_name="booking_id")
    op.drop_constraint("payments_shipment_id_fkey", "payments", type_="foreignkey")
    op.create_foreign_key(
        "payments_booking_id_fkey",
        "payments",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # clearing_docs
    op.alter_column("clearing_docs", "shipment_id", new_column_name="booking_id")
    op.drop_constraint("clearing_docs_shipment_id_fkey", "clearing_docs", type_="foreignkey")
    op.create_foreign_key(
        "clearing_docs_booking_id_fkey",
        "clearing_docs",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("clearing_docs_shipment_id_key", "clearing_docs", type_="unique")
    op.create_unique_constraint("clearing_docs_booking_id_key", "clearing_docs", ["booking_id"])

    # delivery_points
    op.alter_column("delivery_points", "shipment_id", new_column_name="booking_id")
    op.drop_constraint("delivery_points_shipment_id_fkey", "delivery_points", type_="foreignkey")
    op.create_foreign_key(
        "delivery_points_booking_id_fkey",
        "delivery_points",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # notifications
    op.alter_column("notifications", "shipment_id", new_column_name="booking_id")
    op.drop_constraint("notifications_shipment_id_fkey", "notifications", type_="foreignkey")
    op.create_foreign_key(
        "notifications_booking_id_fkey",
        "notifications",
        "bookings",
        ["booking_id"],
        ["id"],
    )

    # audit_logs — rename column, fix FK, rename composite index
    op.alter_column("audit_logs", "shipment_id", new_column_name="booking_id")
    op.drop_constraint("audit_logs_shipment_id_fkey", "audit_logs", type_="foreignkey")
    op.create_foreign_key(
        "audit_logs_booking_id_fkey",
        "audit_logs",
        "bookings",
        ["booking_id"],
        ["id"],
    )
    op.execute("ALTER INDEX ix_audit_logs_shipment_id RENAME TO ix_audit_logs_booking_id")
    op.execute("ALTER INDEX ix_audit_logs_shipment_time RENAME TO ix_audit_logs_booking_time")

    # Per-column indexes that were named after the old column. ALTER TABLE
    # RENAME doesn't carry indexes with it, so rename them explicitly.
    op.execute("ALTER INDEX ix_shipment_users_shipment_id RENAME TO ix_booking_users_booking_id")
    op.execute("ALTER INDEX ix_delivery_points_shipment_id RENAME TO ix_delivery_points_booking_id")
    op.execute("ALTER INDEX ix_payments_shipment_id RENAME TO ix_payments_booking_id")
    op.execute("ALTER INDEX ix_notifications_shipment_id RENAME TO ix_notifications_booking_id")

    # ── 3. PO ↔ Booking many-to-many junction ─────────────────────────────────
    op.create_table(
        "booking_purchase_orders",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "booking_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", "purchase_order_id"),
    )
    op.create_index(
        "ix_booking_purchase_orders_booking_id",
        "booking_purchase_orders",
        ["booking_id"],
    )
    op.create_index(
        "ix_booking_purchase_orders_purchase_order_id",
        "booking_purchase_orders",
        ["purchase_order_id"],
    )

    # Backfill: every existing PO has a non-null shipment_id pointing at a
    # row that's now called `bookings`. Carry those links into the junction.
    op.execute(
        """
        INSERT INTO booking_purchase_orders (id, booking_id, purchase_order_id, added_at)
        SELECT gen_random_uuid(), shipment_id, id, NOW()
          FROM purchase_orders
         WHERE shipment_id IS NOT NULL
        """
    )

    # Now safe to drop the old direct FK column on PO.
    op.drop_constraint("purchase_orders_shipment_id_fkey", "purchase_orders", type_="foreignkey")
    op.drop_constraint("purchase_orders_shipment_id_key", "purchase_orders", type_="unique")
    op.drop_column("purchase_orders", "shipment_id")

    # ── 4. Invoice retargets at PurchaseOrder ────────────────────────────────
    # Each shipment had at most one PO and at most one invoice (old 1:1:1).
    # Add the new column, backfill, then drop the old one.
    op.add_column(
        "invoices",
        sa.Column(
            "purchase_order_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE invoices i
           SET purchase_order_id = po.id
          FROM booking_purchase_orders bpo
          JOIN purchase_orders po ON po.id = bpo.purchase_order_id
         WHERE bpo.booking_id = i.shipment_id
        """
    )
    # Lock down the new column and add the unique 1:1 constraint.
    op.alter_column("invoices", "purchase_order_id", nullable=False)
    op.create_foreign_key(
        "invoices_purchase_order_id_fkey",
        "invoices",
        "purchase_orders",
        ["purchase_order_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("invoices_purchase_order_id_key", "invoices", ["purchase_order_id"])
    op.drop_constraint("invoices_shipment_id_fkey", "invoices", type_="foreignkey")
    op.drop_constraint("invoices_shipment_id_key", "invoices", type_="unique")
    op.drop_column("invoices", "shipment_id")

    # ── 5. Rename the ShipmentStatus enum type ───────────────────────────────
    # Same values, just relabel so the schema reads cleanly. Postgres ENUM
    # rename is a metadata-only change.
    op.execute("ALTER TYPE shipmentstatus RENAME TO bookingstatus")

    # ── 6. RLS on the new junction table ─────────────────────────────────────
    # The other tables keep their RLS state through ALTER RENAME, but the
    # new junction needs it set explicitly to match the deny-all default.
    op.execute("ALTER TABLE booking_purchase_orders ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Reverse, top-to-bottom. NB: multi-PO bookings created after upgrade
    # cannot be expressed in the old 1:1 schema — those rows must be
    # reconciled manually before the downgrade succeeds, otherwise the
    # `purchase_orders.shipment_id` add will fail uniqueness.

    op.execute("ALTER TABLE booking_purchase_orders DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TYPE bookingstatus RENAME TO shipmentstatus")

    # Restore invoices.shipment_id from the junction.
    op.add_column(
        "invoices",
        sa.Column(
            "shipment_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE invoices i
           SET shipment_id = bpo.booking_id
          FROM booking_purchase_orders bpo
         WHERE bpo.purchase_order_id = i.purchase_order_id
        """
    )
    op.alter_column("invoices", "shipment_id", nullable=False)
    op.create_foreign_key(
        "invoices_shipment_id_fkey",
        "invoices",
        "bookings",
        ["shipment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("invoices_shipment_id_key", "invoices", ["shipment_id"])
    op.drop_constraint("invoices_purchase_order_id_fkey", "invoices", type_="foreignkey")
    op.drop_constraint("invoices_purchase_order_id_key", "invoices", type_="unique")
    op.drop_column("invoices", "purchase_order_id")

    # Restore purchase_orders.shipment_id from the junction.
    op.add_column(
        "purchase_orders",
        sa.Column(
            "shipment_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE purchase_orders po
           SET shipment_id = bpo.booking_id
          FROM booking_purchase_orders bpo
         WHERE bpo.purchase_order_id = po.id
        """
    )
    op.alter_column("purchase_orders", "shipment_id", nullable=False)
    op.create_foreign_key(
        "purchase_orders_shipment_id_fkey",
        "purchase_orders",
        "bookings",
        ["shipment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "purchase_orders_shipment_id_key", "purchase_orders", ["shipment_id"]
    )

    # Tear down the junction.
    op.drop_index("ix_booking_purchase_orders_purchase_order_id", "booking_purchase_orders")
    op.drop_index("ix_booking_purchase_orders_booking_id", "booking_purchase_orders")
    op.drop_table("booking_purchase_orders")

    # Reverse the column / FK renames on child tables.
    op.execute("ALTER INDEX ix_notifications_booking_id RENAME TO ix_notifications_shipment_id")
    op.execute("ALTER INDEX ix_payments_booking_id RENAME TO ix_payments_shipment_id")
    op.execute("ALTER INDEX ix_delivery_points_booking_id RENAME TO ix_delivery_points_shipment_id")
    op.execute("ALTER INDEX ix_booking_users_booking_id RENAME TO ix_shipment_users_shipment_id")
    op.execute("ALTER INDEX ix_audit_logs_booking_time RENAME TO ix_audit_logs_shipment_time")
    op.execute("ALTER INDEX ix_audit_logs_booking_id RENAME TO ix_audit_logs_shipment_id")
    op.drop_constraint("audit_logs_booking_id_fkey", "audit_logs", type_="foreignkey")
    op.alter_column("audit_logs", "booking_id", new_column_name="shipment_id")
    op.create_foreign_key(
        "audit_logs_shipment_id_fkey",
        "audit_logs",
        "bookings",
        ["shipment_id"],
        ["id"],
    )

    op.drop_constraint("notifications_booking_id_fkey", "notifications", type_="foreignkey")
    op.alter_column("notifications", "booking_id", new_column_name="shipment_id")
    op.create_foreign_key(
        "notifications_shipment_id_fkey",
        "notifications",
        "bookings",
        ["shipment_id"],
        ["id"],
    )

    op.drop_constraint("delivery_points_booking_id_fkey", "delivery_points", type_="foreignkey")
    op.alter_column("delivery_points", "booking_id", new_column_name="shipment_id")
    op.create_foreign_key(
        "delivery_points_shipment_id_fkey",
        "delivery_points",
        "bookings",
        ["shipment_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("clearing_docs_booking_id_key", "clearing_docs", type_="unique")
    op.drop_constraint("clearing_docs_booking_id_fkey", "clearing_docs", type_="foreignkey")
    op.alter_column("clearing_docs", "booking_id", new_column_name="shipment_id")
    op.create_foreign_key(
        "clearing_docs_shipment_id_fkey",
        "clearing_docs",
        "bookings",
        ["shipment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("clearing_docs_shipment_id_key", "clearing_docs", ["shipment_id"])

    op.drop_constraint("payments_booking_id_fkey", "payments", type_="foreignkey")
    op.alter_column("payments", "booking_id", new_column_name="shipment_id")
    op.create_foreign_key(
        "payments_shipment_id_fkey",
        "payments",
        "bookings",
        ["shipment_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("bills_of_lading_booking_id_key", "bills_of_lading", type_="unique")
    op.drop_constraint("bills_of_lading_booking_id_fkey", "bills_of_lading", type_="foreignkey")
    op.alter_column("bills_of_lading", "booking_id", new_column_name="shipment_id")
    op.create_foreign_key(
        "bills_of_lading_shipment_id_fkey",
        "bills_of_lading",
        "bookings",
        ["shipment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "bills_of_lading_shipment_id_key", "bills_of_lading", ["shipment_id"]
    )

    op.drop_constraint("invite_tokens_booking_id_fkey", "invite_tokens", type_="foreignkey")
    op.alter_column("invite_tokens", "booking_id", new_column_name="shipment_id")
    op.create_foreign_key(
        "invite_tokens_shipment_id_fkey",
        "invite_tokens",
        "bookings",
        ["shipment_id"],
        ["id"],
    )

    op.drop_constraint("booking_users_booking_id_user_id_key", "booking_users", type_="unique")
    op.drop_constraint("booking_users_booking_id_fkey", "booking_users", type_="foreignkey")
    op.alter_column("booking_users", "booking_id", new_column_name="shipment_id")
    op.create_foreign_key(
        "shipment_users_shipment_id_fkey",
        "booking_users",
        "bookings",
        ["shipment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "shipment_users_shipment_id_user_id_key",
        "booking_users",
        ["shipment_id", "user_id"],
    )

    # Bookings → shipments.
    op.drop_index("ix_bookings_booking_number", "bookings")
    op.drop_column("bookings", "booking_number")
    op.rename_table("booking_users", "shipment_users")
    op.rename_table("bookings", "shipments")
