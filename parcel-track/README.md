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

# 2. Copy the environment template and fill in storage/push credentials
cp .env.example .env
# Edit .env — at minimum, generate a SECRET_KEY:
#   python -c "import secrets; print(secrets.token_hex(32))"

# 3. Boot the full stack (Postgres, Redis, API, Celery worker, Celery beat)
docker compose up -d

# 4. Run database migrations (one-time after first boot or schema changes)
docker compose run --rm api alembic upgrade head

# 5. Verify
curl http://localhost:8000/health
# {"status":"ok","env":"development"}
```

The API service bind-mounts `./app` for hot reload — code changes take effect immediately without rebuilding.

## Quick start (local, no Docker)

```bash
# 1. Install dependencies (requires uv: https://docs.astral.sh/uv/)
uv sync --group dev

# 2. Copy and configure .env (see above)
cp .env.example .env

# 3. Start Postgres and Redis however you prefer, then:
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

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
the API only stores the object key. Bucket + token are managed by the account
admin; the values below go in `.env`:

```
STORAGE_BUCKET=parceltrack-documents
STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
STORAGE_ACCESS_KEY_ID=<R2 access key id>
STORAGE_SECRET_ACCESS_KEY=<R2 secret access key>
STORAGE_REGION=auto
STORAGE_PUBLIC_URL=https://<account-id>.r2.cloudflarestorage.com/parceltrack-documents
```

CORS on the bucket must allow `PUT` and `GET` from the mobile app origin.
Use `*` for `AllowedOrigins` during development, then lock it down to the
real app origin before production.

Verify the round-trip end-to-end (uploads bytes, HEAD-checks them, downloads
and compares, then cleans up):

```bash
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

See `/docs` (dev only) for the full OpenAPI spec.

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
