"""backfill: lowercase users.email and invite_tokens.email

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-05-26 12:00:00.000000

Companion to the Pydantic-layer normalization in `app/schemas/schemas.py`
that lowercases `LoginRequest.email` / `InviteRequest.email`. Existing rows
written before that change may carry mixed-case addresses; left alone, the
case-insensitive login path would still match them (because new logins are
lowercased) but legacy lookups by email — `accept_invite`'s
"already registered" check, the bootstrap script's idempotency check, any
audit-time SQL — would treat e.g. `Foo@x.com` and `foo@x.com` as distinct.
Lowercase once and the model is uniform.

Pre-check: if two existing users would collide on `lower(email)` the
migration aborts with a clear error rather than triggering a unique-constraint
violation mid-update. Operator must resolve the duplicate manually.

Downgrade is a no-op — case information is not recoverable.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    collisions = conn.exec_driver_sql(
        "SELECT lower(email) AS norm, count(*) AS n FROM users "
        "GROUP BY lower(email) HAVING count(*) > 1"
    ).fetchall()
    if collisions:
        listing = ", ".join(f"{row.norm!r} ({row.n} rows)" for row in collisions)
        raise RuntimeError(
            "Cannot lowercase users.email: case-collision on "
            f"{listing}. Resolve duplicates manually before re-running."
        )

    conn.exec_driver_sql("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    conn.exec_driver_sql(
        "UPDATE invite_tokens SET email = lower(email) WHERE email <> lower(email)"
    )


def downgrade() -> None:
    # Lowercasing is one-way; the original casing is not recoverable.
    pass
