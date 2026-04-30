# CLAUDE.md — parcel-tracker

## Core Principles
- Simplicity first. No laziness. Senior developer standards.
- Before every response: would a senior dev approve this?
- Business logic belongs in the service layer — never in route handlers.
- All state transitions go through `ShipmentService.transition_status()`. Do not bypass it.

## Bug Fixing Rules
- When given a bug: read logs, find the error, trace root cause, resolve, run test.
- Check `app/core/logging.py` for structured JSON logs + `request_id` context.
- Only ask clarifying questions if you genuinely cannot determine the issue.

## Task Management Rules
- Write plan to `tasks/todo.md` before any implementation.
- Check in before building, mark items done as you go.
- Never start a new task without updating the task file.

## Commit Rules
- Stage only files directly required by the feature or fix: source code, migrations, tests, and env/config documentation (e.g. `.env.example`).
- Do not commit planning artifacts (`tasks/todo.md`, scratch notes, etc.).

## Planning Rules
- Enter plan mode for any 3+ step task.
- Outline every step before writing code.
- Wait for approval before implementation.

## Verification Rules
- Never mark done without proving it works.
- Run tests, check logs, diff changes before reporting completion.
- Run tests with: `uv run pytest tests/ -q`

## Subagent Rules
- Use subagents to keep the main context window clean.
- Offload research, exploration, and parallel tasks.
- Reserve the main thread for decisions and implementation.

## Learning Rules
- After any correction, update `tasks/lessons.md`.
- Review `tasks/lessons.md` at the start of every session.
- Never repeat a documented mistake.

---

## What this project is

Mobile-first supply chain tracker for the end-to-end import process: products shipped
from Morocco to the UK via container shipping. Built for internal business use (not a
commercial product). Four parties: Admin, Morocco logistics agent, UK clearing/delivery
agent, and end customers.

## Working directory

```
/Users/adamfeldman/parcel-tracker/parcel-track
```

All commands run from here unless otherwise noted.

---

## Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.111 + Python 3.12 |
| Database | PostgreSQL via Supabase |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Migrations | Alembic |
| Auth | JWT (python-jose) + bcrypt (passlib) + Redis-backed token revocation |
| File storage | Cloudflare R2 (S3-compatible, boto3) — code wired, creds pending |
| Background jobs | Celery 5.4 + Redis |
| Rate limiting | slowapi (Redis-backed) |
| Package manager | `uv` + `uv.lock` (committed) |
| Mobile frontend | Expo (React Native) — not yet started |

---

## Architecture invariants

- **Containers track state independently from BL upload onward.** Individual containers
  can clear customs at different times. The shipment-level `CLEARED` state only advances
  when the *last* container clears — the shipment never advances prematurely.
- **FastAPI is the real security layer.** RLS is enabled on every public table with
  zero policies, which denies the Supabase `anon`/`authenticated` roles by default.
  The FastAPI runtime role has `BYPASSRLS`, so application queries are unaffected.
  Authorization beyond that (per-user/per-role checks) lives entirely in FastAPI
  middleware and the service layer. Do **not** add allow-all policies — they
  re-open PostgREST to the public anon key.
- **Presigned URL pattern for file uploads.** The server never proxies file bytes.
  Client gets a presigned PUT URL from FastAPI → PUTs directly to R2 → POSTs confirm
  back to FastAPI.
- **R2 is S3-compatible.** All `boto3` / "S3" references in code are intentional — not
  errors. R2 credentials are placeholders in `.env` until the CF account is set up.
- **Single-funnel state machine.** Every shipment transition routes through
  `ShipmentService.transition_status()`, which enforces `VALID_TRANSITIONS` and
  per-state preconditions, then writes an `AuditLog` row. Do not bypass this.
- **Trusted-proxy-aware IP resolution.** `X-Forwarded-For` is only honoured in
  production when the direct peer matches a configured trusted proxy. Used by both
  rate limiter and audit log for consistency.
- **Audit log is append-only and cross-cutting.** State transitions, auth events,
  and sensitive mutations write an `AuditLog` row with actor_id, action, entity,
  old/new values, and client IP. Treat this table as the source of truth for "what
  happened" — never delete or mutate rows in it.

---

## Shipment state machine

`DRAFT → PO_SUBMITTED → INVOICE_RECEIVED → PAYMENT_CONFIRMED → BL_ISSUED →
IN_TRANSIT → CLEARED → COMPLETE`

All transitions enforced in `app/services/shipment_service.py`. Do not move logic
into route handlers.

---

## Critical files

| Concern | Path |
|---|---|
| Entry point, CORS, router mounts, exception handlers | `app/main.py` |
| Per-resource route files (13 modules) | `app/api/routes/` — auth, bl, clearing, containers, customs, delivery, documents, invoices, notifications, payments, po, shipments, vessels |
| State machine — read before touching transitions | `app/services/shipment_service.py` |
| Auth service — JWT issue, bcrypt hashing, refresh | `app/services/auth_service.py` |
| Auth guards + financial masking | `app/middleware/auth.py` |
| JWT revocation + Redis client | `app/core/redis.py` |
| Trusted-proxy IP resolution | `app/core/network.py` |
| Settings + boot-time validation | `app/core/config.py` |
| Structured JSON logging + `request_id` contextvar | `app/core/logging.py` |
| ORM models (incl. AuditLog, CustomsRecord, CustomsNote, VesselUpdate, DeliverySchedule, DeliveryContainer) | `app/db/models.py` |
| DB engine + session factory | `app/db/database.py` |
| Celery tasks + beat schedule | `app/background/tasks.py` |
| Storage (presigned URLs) | `app/services/storage_service.py` |
| Notification dispatch — push enqueued via Celery (`send_push_notification.delay`) | `app/services/notification_service.py` |
| PO / Invoice / Payment services | `app/services/po_service.py`, `invoice_service.py`, `payment_service.py` |
| Container / Customs / Clearing / Delivery services | `app/services/container_service.py`, `customs_service.py`, `clearing_service.py`, `delivery_service.py` |
| Idempotency dependency | `app/middleware/idempotency.py` |
| Rate limiter config | `app/middleware/rate_limit.py` |
| Security headers middleware | `app/middleware/security_headers.py` |
| Request logging + `request_id` propagation | `app/middleware/request_logging.py` |
| Initial schema migration | `app/db/migrations/versions/56df7eb7f236_initial_schema.py` |
| P1 indexes + CHECK constraints | `app/db/migrations/versions/a1b2c3d4e5f6_p1_indexes_and_constraints.py` |
| CI pipeline | `.github/workflows/ci.yml` |
| Dependency manifest + tool config | `pyproject.toml` |
| Roadmap / task specs | `docs/ROADMAP.md` |

---

## Language & runtime rules

### Package manager (`uv`)

This project uses `pyproject.toml` + `uv.lock`. There is **no** `requirements.txt` —
never run `uv pip install -r requirements.txt`.

```bash
uv sync --frozen --group dev               # install from lockfile
uv run pytest tests/ -q                    # any tool runs via `uv run`
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
uv sync --group dev                        # recompute lockfile after pyproject change
```

### Database: two URIs

| Context | URI format | Why |
|---|---|---|
| Alembic migrations (`DATABASE_URL_SYNC`) | `postgresql://...` | sync driver |
| FastAPI runtime (`DATABASE_URL`) | `postgresql+asyncpg://...` | async requires asyncpg |

Both must be set. Never swap them. Production `config.py` validates that
`DATABASE_URL` starts with `postgresql+asyncpg://`.

### SQLAlchemy async

- `expire_on_commit=False` is set on the session factory in `app/db/database.py` —
  without it, ORM objects detach after commit and crash on attribute access.
- Never use lazy loading. Always `selectinload` relationships — lazy loading raises
  `MissingGreenlet` in async context.
- `db.flush()` sends SQL within an open transaction (no commit). `db.commit()` makes
  it permanent. Use `flush()` when you need a DB-generated ID mid-transaction.
- After `db.refresh()`, relationships may be expired — refetch with explicit
  `selectinload` when serialising (see `upload_bl` in `routes.py` for the pattern).

---

## Common gotchas

| Mistake | Correct approach |
|---|---|
| `uv pip install -r requirements.txt` | Use `uv sync --frozen --group dev` — this project uses `pyproject.toml` |
| `+asyncpg` in Alembic URL | Alembic needs `DATABASE_URL_SYNC` = plain `postgresql://` |
| Lazy loading ORM relationships | Always use `selectinload` — lazy loading crashes async |
| Missing `expire_on_commit=False` | Sessions close and objects detach — already set in `database.py` |
| Business logic in route handlers | All logic in service layer; routes only validate + call services |
| Returning ORM objects directly | Always use `response_model=` with Pydantic schemas |
| R2 "S3" references look wrong | They are correct — R2 is S3-compatible, boto3 is the right client |
| Supabase RLS warnings | RLS is enabled with no policies (deny-all). FastAPI runs as a BYPASSRLS role, so app queries still work. Do **not** add allow-all policies — they re-open PostgREST to the public anon key |
| Trusting `X-Forwarded-For` blindly | Goes through `app/core/network.py` — only honoured in prod behind a trusted proxy |
| Forgetting `Idempotency-Key` on `POST /payments` or `POST /invoices` | Returns 400. All clients must generate and send a UUID per logical request |

---

## Current status & next work

**P0** — COMPLETE (PR #6, `main` at `09da227`).
**P1** — Tasks 1, 2, 3, 5 merged (HTTP resilience, Celery push, R2 end-to-end, VesselFinder polling). Task 4 (Destin8) still blocked on tier/credentials.
**P2** — COMPLETE. All 7 hardening items done as of `p2-service-layer`.
**P2.5** — RLS enabled on all 22 public tables (migration `5ab45b2e1574`, branch `p2-supabase-rls`).
**P3** — TODO.

Full task specs (acceptance criteria, file lists, poller algorithms) live in
[`docs/ROADMAP.md`](docs/ROADMAP.md). Summary of remaining open work below.

| # | Item | Status | Blocker |
|---|---|---|---|
| P1.4 | Destin8 polling worker | BLOCKED | API credentials + tier choice |
| P3 | Read caching, soft delete, API versioning, `/docs` lockdown, TZ audit, locust load test | TODO | product decisions |

### Open decisions (gate the blocked items)

1. Destin8 tier + endpoint URL (gates P1.4)
2. Hosting target — Fly.io vs Railway (both run the Dockerfile as api + worker + beat)
3. Data retention / GDPR policy (drives P3 soft-delete work)

---

## GitHub

- Repo: `Adamleefeldman/parcel-track`. `main` is source of truth — always sync before branching.
- One branch + PR per roadmap task. CI runs ruff (blocking), pytest against a real
  Postgres service container (blocking), and mypy (non-blocking until P2).
