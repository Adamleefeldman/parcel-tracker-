#!/usr/bin/env python3
"""
Bootstrap the first ADMIN user in a fresh ParcelTrack database.

The auth flow is invite-based: admins create other users via the invite
endpoint. That leaves a chicken-and-egg problem on a fresh DB — no one can
issue invites because no admin exists. This script breaks the cycle by
inserting a single ADMIN row directly, using the same password hashing the
app uses at runtime.

By convention the host ``.env`` points at the LOCAL Docker stack
(``DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/parceltrack``),
so running this script from the host writes to the same database the
``parceltrack-api`` container reads from. No special invocation needed:

    uv run python scripts/bootstrap_admin.py

To seed production Supabase instead, pass the explicit override file:

    uv run --env-file .env.supabase python scripts/bootstrap_admin.py --i-mean-it

The script auto-detects when the resolved DB and the running api
container target *different* databases (typically: host loaded
``.env.supabase`` while compose is still up) and refuses to run unless
``--i-mean-it`` is passed.

Usage::

    # Reads ADMIN_EMAIL / ADMIN_NAME / ADMIN_PASSWORD from env if set,
    # otherwise prompts interactively (password input is hidden).
    uv run python scripts/bootstrap_admin.py

    # One-shot non-interactive:
    ADMIN_EMAIL=ops@example.com \\
    ADMIN_NAME="Ops Admin" \\
    ADMIN_PASSWORD='...' \\
    uv run python scripts/bootstrap_admin.py

    # Override the docker/host mismatch guard (only if you really mean
    # to target the host-resolved DATABASE_URL while the compose stack
    # is up — e.g. seeding Supabase from the host on purpose):
    uv run python scripts/bootstrap_admin.py --i-mean-it

Idempotent: if a user with that email already exists, the script exits 0
with a notice. Safe to re-run. It will NOT promote an existing non-admin
user to ADMIN — that's a separate concern handled via direct SQL or a
future admin-role-change endpoint.

Targets whichever database ``DATABASE_URL`` points at. Run with the
production env loaded to seed production.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from getpass import getpass
from pathlib import Path
from urllib.parse import urlparse

# Ensure the project root is on sys.path so `app` is importable when this
# script is run directly with `uv run python scripts/bootstrap_admin.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.database import AsyncSessionLocal
from app.db.models import User

_MIN_PASSWORD_LEN = 12
_COMPOSE_API_CONTAINER = "parceltrack-api"
_DOCKER_PROBE_TIMEOUT_SEC = 2.0


def _db_target(url: str) -> str:
    """Return ``host:port/dbname`` for a SQLAlchemy/Postgres URL, or the raw URL on parse failure.

    Used for human-readable diagnostic output. Equality comparison goes
    through :func:`_db_identity` instead, which ignores hostname so that
    ``localhost`` (host-side) and ``postgres`` (compose-internal) resolve
    as the same database when port and dbname match.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or 5432
        dbname = (parsed.path or "/").lstrip("/") or "?"
        return f"{host}:{port}/{dbname}"
    except (ValueError, TypeError):
        return url


def _db_identity(url: str) -> tuple[int, str]:
    """Return ``(port, dbname)`` — the equality key for DB comparison.

    Hostname is intentionally excluded so the host-side URL
    (``localhost:5432/parceltrack``) is treated as equivalent to the
    compose-internal URL (``postgres:5432/parceltrack``) when both refer
    to the same compose Postgres service. A real mismatch (host pointed
    at Supabase via ``.env.supabase`` while compose still runs locally)
    differs in both port and dbname, so the safeguard still fires.
    """
    try:
        parsed = urlparse(url)
        port = parsed.port or 5432
        dbname = (parsed.path or "/").lstrip("/")
        return port, dbname
    except (ValueError, TypeError):
        return 0, url


def _detect_db_mismatch(resolved_db_url: str) -> tuple[str, str] | None:
    """Detect the host-vs-compose-container DB mismatch trap.

    Returns ``(host_target, container_target)`` if the local ``parceltrack-api``
    compose container is running AND its ``DATABASE_URL`` points at a different
    host:port than the script's own resolved URL. Returns ``None`` if docker is
    not installed, the container is not running, the probe fails, or both URLs
    agree — in any of those cases the host run is the correct target.
    """
    # Fixed argv, no shell, no user input. `docker` is intentionally resolved
    # via PATH because this is a developer-machine script, not server code.
    ps_argv = ["docker", "ps", "--format", "{{.Names}}"]
    try:
        ps = subprocess.run(  # noqa: S603
            ps_argv,
            capture_output=True,
            text=True,
            timeout=_DOCKER_PROBE_TIMEOUT_SEC,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if ps.returncode != 0:
        return None
    running = {line.strip() for line in ps.stdout.splitlines() if line.strip()}
    if _COMPOSE_API_CONTAINER not in running:
        return None

    exec_argv = ["docker", "exec", _COMPOSE_API_CONTAINER, "printenv", "DATABASE_URL"]
    try:
        env = subprocess.run(  # noqa: S603
            exec_argv,
            capture_output=True,
            text=True,
            timeout=_DOCKER_PROBE_TIMEOUT_SEC,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if env.returncode != 0:
        return None
    container_url = env.stdout.strip()
    if not container_url:
        return None

    if _db_identity(container_url) == _db_identity(resolved_db_url):
        return None
    return resolved_db_url, container_url


def _read_admin_inputs() -> tuple[str, str, str]:
    """Pull email / name / password from env, falling back to prompts."""
    email = os.environ.get("ADMIN_EMAIL") or input("Admin email: ").strip()
    name = os.environ.get("ADMIN_NAME") or input("Admin name: ").strip()
    password = os.environ.get("ADMIN_PASSWORD") or getpass("Admin password: ")

    if not email or "@" not in email:
        print("ERROR: a valid email is required.", file=sys.stderr)
        sys.exit(2)
    if not name:
        print("ERROR: a non-empty name is required.", file=sys.stderr)
        sys.exit(2)
    if len(password) < _MIN_PASSWORD_LEN:
        print(
            f"ERROR: password must be at least {_MIN_PASSWORD_LEN} characters.",
            file=sys.stderr,
        )
        sys.exit(2)

    return email.lower(), name, password


async def _bootstrap(email: str, name: str, password: str) -> int:
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            if existing.role == UserRole.ADMIN:
                print(f"OK: admin {email!r} already exists (id={existing.id}). Nothing to do.")
            else:
                print(
                    f"NOTICE: user {email!r} already exists with role "
                    f"{existing.role.value!r}, not ADMIN. Refusing to silently "
                    "promote — change the role via SQL or build an admin "
                    "role-change flow.",
                    file=sys.stderr,
                )
                return 1
            return 0

        user = User(
            email=email,
            name=name,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"OK: created admin {email!r} (id={user.id}).")
        return 0


def _warn_mismatch(host_url: str, container_url: str) -> None:
    print(
        "\n"
        "  ============================================================\n"
        "  WARNING: docker/host DATABASE_URL mismatch detected\n"
        "  ============================================================\n"
        f"  This script (host)        → {_db_target(host_url)}\n"
        f"  parceltrack-api container → {_db_target(container_url)}\n"
        "\n"
        "  Your compose stack is running, but its api container is\n"
        "  pointed at a different database than the one this script\n"
        "  resolved from the host .env. Seeding here will NOT create\n"
        "  a user the local API can see — login will return 401.\n"
        "\n"
        "  To seed the database the local API actually uses, re-run\n"
        "  inside the api container:\n"
        "\n"
        "    docker exec -it parceltrack-api uv run python scripts/bootstrap_admin.py\n"
        "\n"
        "  If you really do want to target the host-resolved DB (e.g.\n"
        "  seeding Supabase on purpose), re-run with --i-mean-it.\n"
        "  ============================================================\n",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    override = "--i-mean-it" in args

    resolved_db_url = get_settings().DATABASE_URL
    mismatch = _detect_db_mismatch(resolved_db_url)
    if mismatch is not None and not override:
        _warn_mismatch(*mismatch)
        return 2

    email, name, password = _read_admin_inputs()
    return asyncio.run(_bootstrap(email, name, password))


if __name__ == "__main__":
    sys.exit(main())
