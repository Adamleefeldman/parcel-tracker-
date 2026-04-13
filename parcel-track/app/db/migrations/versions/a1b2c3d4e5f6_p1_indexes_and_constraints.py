"""p1 indexes and constraints

Revision ID: a1b2c3d4e5f6
Revises: 56df7eb7f236
Create Date: 2026-04-13 00:00:00.000000

Adds:
  Indexes
  - delivery_containers.delivery_point_id
  - delivery_containers.container_id
  - documents (entity_type, entity_id)  [composite]
  - audit_logs.actor_id
  - audit_logs (shipment_id, created_at)  [composite]
  - audit_logs (actor_id, created_at)    [composite]
  - notifications.shipment_id

  CHECK constraints (database-level safety net for numeric fields)
  - purchase_orders: quantity >= 0, total_value >= 0
  - invoices: value >= 0
  - payments: amount > 0
  - bills_of_lading: container_count > 0, gross_weight_kg > 0
  - clearing_docs: duty_rate >= 0 (nullable), estimated_duty_vat >= 0 (nullable)
  - customs_records: duty_paid >= 0 (nullable)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "56df7eb7f236"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Indexes: delivery_containers FKs ─────────────────────────────────────
    op.create_index(
        "ix_delivery_containers_delivery_point_id",
        "delivery_containers",
        ["delivery_point_id"],
    )
    op.create_index(
        "ix_delivery_containers_container_id",
        "delivery_containers",
        ["container_id"],
    )

    # ── Index: documents composite (entity_type, entity_id) ──────────────────
    op.create_index(
        "ix_documents_entity",
        "documents",
        ["entity_type", "entity_id"],
    )

    # ── Indexes: audit_logs actor + composites ────────────────────────────────
    op.create_index(
        "ix_audit_logs_actor_id",
        "audit_logs",
        ["actor_id"],
    )
    op.create_index(
        "ix_audit_logs_shipment_time",
        "audit_logs",
        ["shipment_id", "created_at"],
    )
    op.create_index(
        "ix_audit_logs_actor_time",
        "audit_logs",
        ["actor_id", "created_at"],
    )

    # ── Index: notifications.shipment_id ─────────────────────────────────────
    op.create_index(
        "ix_notifications_shipment_id",
        "notifications",
        ["shipment_id"],
    )

    # ── CHECK constraints: purchase_orders ───────────────────────────────────
    op.create_check_constraint(
        "ck_purchase_orders_quantity_non_negative",
        "purchase_orders",
        sa.text("quantity >= 0"),
    )
    op.create_check_constraint(
        "ck_purchase_orders_total_value_non_negative",
        "purchase_orders",
        sa.text("total_value >= 0"),
    )

    # ── CHECK constraint: invoices ────────────────────────────────────────────
    op.create_check_constraint(
        "ck_invoices_value_non_negative",
        "invoices",
        sa.text("value >= 0"),
    )

    # ── CHECK constraint: payments ────────────────────────────────────────────
    op.create_check_constraint(
        "ck_payments_amount_positive",
        "payments",
        sa.text("amount > 0"),
    )

    # ── CHECK constraints: bills_of_lading ───────────────────────────────────
    op.create_check_constraint(
        "ck_bills_of_lading_container_count_positive",
        "bills_of_lading",
        sa.text("container_count > 0"),
    )
    op.create_check_constraint(
        "ck_bills_of_lading_gross_weight_positive",
        "bills_of_lading",
        sa.text("gross_weight_kg > 0"),
    )

    # ── CHECK constraints: clearing_docs (nullable columns) ──────────────────
    op.create_check_constraint(
        "ck_clearing_docs_duty_rate_non_negative",
        "clearing_docs",
        sa.text("duty_rate IS NULL OR duty_rate >= 0"),
    )
    op.create_check_constraint(
        "ck_clearing_docs_estimated_duty_vat_non_negative",
        "clearing_docs",
        sa.text("estimated_duty_vat IS NULL OR estimated_duty_vat >= 0"),
    )

    # ── CHECK constraint: customs_records (nullable column) ───────────────────
    op.create_check_constraint(
        "ck_customs_records_duty_paid_non_negative",
        "customs_records",
        sa.text("duty_paid IS NULL OR duty_paid >= 0"),
    )


def downgrade() -> None:
    # ── Remove CHECK constraints ──────────────────────────────────────────────
    op.drop_constraint(
        "ck_customs_records_duty_paid_non_negative", "customs_records", type_="check"
    )
    op.drop_constraint(
        "ck_clearing_docs_estimated_duty_vat_non_negative", "clearing_docs", type_="check"
    )
    op.drop_constraint("ck_clearing_docs_duty_rate_non_negative", "clearing_docs", type_="check")
    op.drop_constraint("ck_bills_of_lading_gross_weight_positive", "bills_of_lading", type_="check")
    op.drop_constraint(
        "ck_bills_of_lading_container_count_positive", "bills_of_lading", type_="check"
    )
    op.drop_constraint("ck_payments_amount_positive", "payments", type_="check")
    op.drop_constraint("ck_invoices_value_non_negative", "invoices", type_="check")
    op.drop_constraint(
        "ck_purchase_orders_total_value_non_negative", "purchase_orders", type_="check"
    )
    op.drop_constraint("ck_purchase_orders_quantity_non_negative", "purchase_orders", type_="check")

    # ── Remove indexes ────────────────────────────────────────────────────────
    op.drop_index("ix_notifications_shipment_id", table_name="notifications")
    op.drop_index("ix_audit_logs_actor_time", table_name="audit_logs")
    op.drop_index("ix_audit_logs_shipment_time", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_documents_entity", table_name="documents")
    op.drop_index("ix_delivery_containers_container_id", table_name="delivery_containers")
    op.drop_index("ix_delivery_containers_delivery_point_id", table_name="delivery_containers")
