"""Guard against NotificationType enum / migration drift.

The Postgres `notificationtype` enum is built by the Alembic migration chain, but
the test suite builds its schema from `Base.metadata.create_all` — so a member
added to the Python enum without a matching migration is INVISIBLE to every other
test, yet raises a `DataError` (and rolls back the request) on real Postgres.

This closes that gap by checking the migration chain statically: the set of
`notificationtype` labels the migrations' `upgrade()` paths produce must equal the
labels SQLAlchemy expects for the model. `Notification.type` uses the default
name-bound `SAEnum`, so the expected labels are the member *names* (uppercase).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.enums import NotificationType

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "app" / "db" / "migrations" / "versions"
_ENUM_NAME = "notificationtype"

# Only scan the upgrade() path; downgrade() may reverse renames and would skew the
# reconstructed set. `[^()]` in the create matcher keeps the body inside a single
# sa.Enum(...) call (label literals contain no parentheses).
_UPGRADE_RE = re.compile(r"def upgrade\(\).*?(?=\ndef downgrade\(\)|\Z)", re.S)
_CREATE_RE = re.compile(r"sa\.Enum\(([^()]*?)name=[\"']" + _ENUM_NAME + r"[\"']")
_ADD_RE = re.compile(
    r"ALTER TYPE\s+" + _ENUM_NAME + r"\s+ADD VALUE(?:\s+IF NOT EXISTS)?\s+'([^']+)'"
)
_RENAME_RE = re.compile(
    r"ALTER TYPE\s+" + _ENUM_NAME + r"\s+RENAME VALUE\s+'([^']+)'\s+TO\s+'([^']+)'"
)
_LITERAL_RE = re.compile(r"[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")


def _labels_from_migrations() -> set[str]:
    """Reconstruct the final notificationtype label set from the migration files.

    Two-pass so file iteration order is irrelevant: collect every created/added
    label first, then apply every RENAME VALUE old -> new.
    """
    labels: set[str] = set()
    renames: list[tuple[str, str]] = []

    for path in _VERSIONS_DIR.glob("*.py"):
        upgrade = _UPGRADE_RE.search(path.read_text())
        if not upgrade:
            continue
        body = upgrade.group(0)
        for enum_body in _CREATE_RE.findall(body):
            labels.update(_LITERAL_RE.findall(enum_body))
        labels.update(_ADD_RE.findall(body))
        renames.extend(_RENAME_RE.findall(body))

    for old, new in renames:
        labels.discard(old)
        labels.add(new)
    return labels


def test_notificationtype_migrations_match_model() -> None:
    expected = {member.name for member in NotificationType}
    migrated = _labels_from_migrations()

    missing = expected - migrated
    extra = migrated - expected

    assert not missing, (
        f"NotificationType members with no matching label in the migration chain "
        f"(inserts of these will fail on Postgres): {sorted(missing)}. "
        f"Add an `ALTER TYPE {_ENUM_NAME} ADD VALUE ...` migration for them."
    )
    assert not extra, (
        f"Migration chain declares {_ENUM_NAME} labels absent from the model: "
        f"{sorted(extra)}. Reconcile the migration with NotificationType."
    )
