"""enable rls on public tables

Revision ID: 5ab45b2e1574
Revises: b2c3d4e5f6a7
Create Date: 2026-04-29 13:50:40.861281

Enables Row Level Security on every public table with no policies attached.

Why: Supabase exposes a PostgREST API on every project, reachable with the
publicly-distributable `anon` key. Without RLS, anyone holding that key can
read or modify rows directly via PostgREST, bypassing FastAPI entirely.

How this works: PostgreSQL's default behaviour for an RLS-enabled table with
zero policies is deny-all. The Supabase `anon` and `authenticated` roles get
no rows. The FastAPI runtime role (`postgres`, configured in DATABASE_URL)
has BYPASSRLS, so application queries are unaffected. Authorization beyond
that lives in FastAPI middleware and the service layer.

Do NOT add allow-all policies on these tables — that re-opens PostgREST to
the public anon key and defeats the purpose of this migration.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ab45b2e1574"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# All public tables in the schema (21 application tables + alembic bookkeeping).
RLS_TABLES: tuple[str, ...] = (
    "users",
    "refresh_tokens",
    "invite_tokens",
    "shipments",
    "shipment_users",
    "purchase_orders",
    "invoices",
    "payments",
    "bills_of_lading",
    "vessels",
    "vessel_updates",
    "containers",
    "clearing_docs",
    "customs_records",
    "customs_notes",
    "delivery_points",
    "delivery_containers",
    "delivery_schedules",
    "documents",
    "audit_logs",
    "notifications",
    "alembic_version",
)


def upgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
