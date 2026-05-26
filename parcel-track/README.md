# ParcelTrack Backend

FastAPI backend for the ParcelTrack shipment tracking platform. Manages the full shipment lifecycle from purchase order through customs clearance to final delivery.

## Stack

- **Runtime**: Python 3.12, FastAPI, Uvicorn (ASGI)
- **Database**: PostgreSQL (async via SQLAlchemy 2.0 + asyncpg)
- **Migrations**: Alembic
- **Auth**: JWT access tokens + refresh token rotation, invite-based registration
- **Background jobs**: Celery + Redis (beat scheduler for deadline checks)
- **File storage**: S3-compatible (Cloudflare R2) via presigned URLs
- **Push notifications**: Expo Push API

## Quick start (Docker)

```bash
# 1. Clone and enter the backend directory
cd parcel-track

# 2. Copy the environment template and configure non-secret values
cp .env.example .env
# Edit .env — at minimum, generate a SECRET_KEY:
#   python -c "import secrets; print(secrets.token_hex(32))"
# Note: STORAGE_ACCESS_KEY_ID and STORAGE_SECRET_ACCESS_KEY do NOT go in
# .env — they are file-backed Docker secrets. See "Cloudflare R2 setup"
# below for how to populate secrets/STORAGE_*.

# 3. Boot the full stack (Postgres, Redis, API, Celery worker, Celery beat)
docker compose up -d

# 4. Run database migrations (one-time after first boot or schema changes)
docker compose run --rm api alembic upgrade head

# 5. Verify
curl http://localhost:8000/health
# {"status":"ok","env":"development"}
```

The API service bind-mounts `./app` for hot reload — code changes take effect immediately without rebuilding.

**`.env` is local-Docker-by-default.** Its `DATABASE_URL` / `DATABASE_URL_SYNC` /
`REDIS_URL` settings point at the localhost-forwarded ports of the compose
services, so any host-run script (`uv run python ...`, ad-hoc Alembic) talks
to the same database the API container talks to. Production Supabase access
requires the explicit flag described in [Running against production
Supabase](#running-against-production-supabase) below.

## Quick start (local, no Docker)

If you prefer to run Postgres/Redis directly on the host (no compose), the
defaults in `.env.example` still apply — they just expect Postgres on
`localhost:5432` (user/pw/db `postgres`/`postgres`/`parceltrack`) and Redis
on `localhost:6379`.

```bash
# 1. Install dependencies (requires uv: https://docs.astral.sh/uv/)
uv sync --group dev

# 2. Copy and configure .env (see above)
cp .env.example .env

# 3. Start Postgres and Redis however you prefer (matching the .env URLs), then:
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

## Running against production Supabase

The default `.env` targets local Docker. To run a host command against the
production Supabase database (or production Upstash Redis), pass an
`--env-file` override and use a gitignored `.env.supabase` containing the
prod URLs:

```bash
# Create .env.supabase from the template (commit-safe values only — no creds):
cat > .env.supabase <<'EOF'
DATABASE_URL=postgresql+asyncpg://<user>:<pw>@<supabase-pooler-host>:5432/postgres
DATABASE_URL_SYNC=postgresql://<user>:<pw>@<supabase-pooler-host>:5432/postgres
# Optional — only if running against prod Upstash:
# REDIS_URL=rediss://default:<token>@<endpoint>.upstash.io:6379
EOF
chmod 600 .env.supabase   # treat as a credentials file

# Use it explicitly per command:
uv run --env-file .env.supabase alembic current
uv run --env-file .env.supabase alembic upgrade head
uv run --env-file .env.supabase python scripts/<your_script>.py
```

`.env.supabase` is gitignored by the existing `.env*` rule. There is **no
default fallback** to prod — without the `--env-file` flag, every host
command stays on local Docker. This is intentional: it prevents the
split-brain mode where a typo'd Alembic downgrade or an ad-hoc `DELETE FROM`
hits production unnoticed.

## Pre-commit hooks (required)

```bash
pip install pre-commit   # or: uv tool install pre-commit
pre-commit install
pre-commit install --hook-type pre-push
```

- **Pre-commit**: ruff lint + format (milliseconds)
- **Pre-push**: mypy type check (seconds)

## Cloudflare R2 setup

File uploads use the presigned-URL pattern: clients PUT directly to R2 and
the API only stores the object key. Bucket + token are managed by the
account admin.

**Non-secret config goes in `.env`** (gitignored):

```
STORAGE_BUCKET=parceltrack-documents
STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
STORAGE_REGION=auto
STORAGE_PUBLIC_URL=https://<account-id>.r2.cloudflarestorage.com/parceltrack-documents
```

**Credentials go in file-backed Docker secrets**, not `.env`. Compose
mounts them at `/run/secrets/<NAME>`; Pydantic-Settings reads them via
`secrets_dir`. Drop the raw values (no quotes, no trailing newline) into:

```bash
printf '%s' '<R2 access key id>'      > secrets/STORAGE_ACCESS_KEY_ID
printf '%s' '<R2 secret access key>'  > secrets/STORAGE_SECRET_ACCESS_KEY
chmod 600 secrets/STORAGE_ACCESS_KEY_ID secrets/STORAGE_SECRET_ACCESS_KEY
```

Both files are gitignored (`/secrets/*` with `!.gitkeep` + `!README.md`
exceptions) and dockerignored — they never enter git or the runtime image.
See `secrets/README.md` for the full convention.

CORS on the bucket must allow `PUT` and `GET` from the mobile app origin.
Use `*` for `AllowedOrigins` during development, then lock it down to the
real app origin before production.

Verify the round-trip end-to-end (uploads bytes, HEAD-checks them,
downloads and compares, then cleans up). Two equivalent ways to run it:

```bash
# Inside a one-shot container — inherits the same secrets the running api
# does. Recommended; never exposes the keys to your host shell.
docker compose run --rm \
  -v "$(pwd)/scripts:/app/scripts:ro" \
  api python scripts/smoke_r2.py

# Or from the host, sourcing the secret files into a single-process env.
env \
  STORAGE_ACCESS_KEY_ID="$(cat secrets/STORAGE_ACCESS_KEY_ID)" \
  STORAGE_SECRET_ACCESS_KEY="$(cat secrets/STORAGE_SECRET_ACCESS_KEY)" \
  uv run python scripts/smoke_r2.py
```

Exits 0 on success, 1 with the failing step on stderr.

## Running tests

```bash
# Local (SQLite in-memory, fast)
uv run pytest tests/ -q

# Against real Postgres (set TEST_DATABASE_URL first)
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/parceltrack_test \
  uv run pytest tests/ -q
```

CI runs tests against a Postgres service container automatically.

## Linting & type checking

```bash
uv run ruff check app/ tests/        # lint
uv run ruff format --check app/ tests/  # format check
uv run mypy app/                      # type check (non-strict for now)
```

## Project structure

```
parcel-track/
  app/
    api/routes/routes.py    # All endpoint handlers
    core/
      config.py             # Pydantic settings (env vars)
      enums.py              # Status enums for all entities
      security.py           # JWT, password hashing
    db/
      database.py           # Async engine + session
      models.py             # 18 SQLAlchemy ORM models
      migrations/            # Alembic
    middleware/
      auth.py               # Role guards, membership checks
      rate_limit.py         # slowapi rate limiting
      security_headers.py   # X-Frame-Options, HSTS, etc.
    schemas/
      schemas.py            # Pydantic request/response models
      pagination.py         # Paginated list envelope
    services/
      auth_service.py       # Invite, login, refresh, logout
      shipment_service.py   # State machine, preconditions
      notification_service.py
      storage_service.py    # S3 presigned URLs
    background/tasks.py     # Celery periodic tasks
    main.py                 # FastAPI app, middleware, routers
  tests/integration/        # pytest-asyncio integration tests
  Dockerfile                # Multi-stage, non-root, 410 MB
  docker-compose.yml        # 5-service local dev stack
  .pre-commit-config.yaml
  pyproject.toml            # Dependencies + ruff/mypy config
```

## Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/ready` | Readiness probe (pings DB) |
| `POST` | `/api/v1/auth/login` | Login (5/min rate limit) |
| `POST` | `/api/v1/auth/invite` | Admin creates invite |
| `GET` | `/api/v1/shipments` | Paginated list (offset, limit, total) |
| `GET` | `/api/v1/shipments/{id}` | Full shipment detail with nested relations |

See `/docs` for the full OpenAPI spec — open in dev/staging, gated behind an admin JWT in production (Phase D1).

## Shipment workflow

```
DRAFT -> PO_SUBMITTED -> INVOICE_RECEIVED -> PAYMENT_CONFIRMED
      -> BL_ISSUED -> IN_TRANSIT -> CLEARED -> COMPLETE
```

Each transition enforces preconditions (e.g. all containers must be cleared before CLEARED) and writes an audit log entry.

## Recommended branch protection (GitHub)

Apply these settings to the `main` branch in the GitHub UI:

- Require a pull request before merging
- Require status checks to pass (select **lint** and **test** jobs)
- Require branches to be up to date before merging
- Do not allow bypassing the above settings

The **typecheck** (mypy) job is non-blocking for now and will become required in P2 once type coverage improves.
