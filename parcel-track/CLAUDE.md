# CLAUDE.md — parcel-tracker

## Core Principles
- Simplicity first. No laziness. Senior developer standards.
- Before every response: would a senior dev approve this?
- Business logic belongs in the service layer — never in route handlers.
- All booking-level state transitions go through `BookingService.transition_status()`. Do not bypass it.
- All container-level lifecycle changes go through `ContainerLifecycleService.recompute()` — never write `Container.lifecycle_status` directly.

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

Mobile-first supply chain tracker for the end-to-end import + resale process of
soft drinks (Pepsi / Mirinda / 7Up) shipped from Casablanca to the UK by **WT
Trading LLC**, trading as **The FMCG Hub**. Built for internal business use (not
a commercial product). Four parties: Admin, Morocco logistics agent, UK
clearing/delivery agent, and end customers. The data model is anchored on the
client's real trading workflow (PO → Booking → Container → Delivery → Customer
Payment) — see `docs/ROADMAP.md` for the trading-core remediation that aligned
the schema with this reality.

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
| Hosting | Railway — https://parcel-tracker-production-477c.up.railway.app (api + worker + beat from single Dockerfile) |

---

## Architecture invariants

- **Container is the operational unit.** Sale price, broker, end-company,
  delivery type, lifecycle state, customer payment — all live on `Container`.
  The Booking aggregates one or more POs and carries the shipping-line booking
  number + BL, but the container is what's actually being moved and sold.
- **One Booking, many POs (and vice versa).** Joined through the
  `booking_purchase_orders` junction table. A carrier booking commonly carries
  more than one PO (e.g. DP World booking 2601008 covers PO-2026-04 +
  PO-2026-05). All booking-level preconditions walk the M:N chain.
- **Containers track state independently from BL upload onward.** Individual
  containers can clear customs at different times. The booking-level `CLEARED`
  state only advances when the *last* container clears — the booking never
  advances prematurely.
- **`COMPLETE` means customer-paid, not just delivered.** A booking only
  reaches `COMPLETE` when every container's `lifecycle_status` is `BANKED`
  (or an acknowledged `DISPUTED`). Marking deliveries `DELIVERED` is necessary
  but not sufficient — the customer-side leg must close too.
- **Two payment directions.** `SupplierPayment` is outbound USD against an
  `Invoice` (one per PO, supplier CI from SCDB). `CustomerPayment` is inbound
  GBP against a `Container`, multi-tranche, with cash/transfer split,
  variance, courier + bank-charge expenses, and a banked total. Never use a
  generic "Payment" — pick the side.
- **Container lifecycle is derived, not pushed.** Concrete events (vessel
  depart/arrive, customs clear, delivery, customer payment) trigger
  `ContainerLifecycleService.recompute(container_id)`, which walks the inputs
  and writes `Container.lifecycle_status`. Do not set the field by hand from
  route handlers.
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
- **Single-funnel state machine.** Every booking transition routes through
  `BookingService.transition_status()`, which enforces `VALID_TRANSITIONS` and
  per-state preconditions, then writes an `AuditLog` row. Do not bypass this.
- **Trusted-proxy-aware IP resolution.** `X-Forwarded-For` is only honoured in
  production when the direct peer matches a configured trusted proxy. Used by both
  rate limiter and audit log for consistency.
- **Audit log is append-only and cross-cutting.** State transitions, auth events,
  and sensitive mutations write an `AuditLog` row with actor_id, action, entity,
  old/new values, and client IP. Treat this table as the source of truth for "what
  happened" — never delete or mutate rows in it.
- **All API routes mount under `/api/v1`.** Single `PREFIX` constant in
  `app/main.py`. `/health`, `/ready`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`
  are intentionally unversioned — they are infrastructure, not API contract. Do
  not register new application endpoints directly on `app` — always go through a
  router mounted at `PREFIX`. Bumping to `/api/v2` is reserved for a real
  incompatible shape change; prefer additive evolution within `/v1`.

---

## Booking state machine

`DRAFT → PO_SUBMITTED → INVOICE_RECEIVED → PAYMENT_CONFIRMED → BL_ISSUED →
IN_TRANSIT → CLEARED → COMPLETE`

All transitions enforced in `app/services/booking_service.py`. Do not move
logic into route handlers. Key preconditions worth knowing:

- `PO_SUBMITTED` — at least one linked PO is `SUBMITTED` (with its document
  uploaded). Booking advances on the first linked PO's submit; later POs can
  attach to the same booking afterwards.
- `INVOICE_RECEIVED` — every linked PO has its supplier `Invoice` in
  `RECEIVED` / `RECONCILED` state. `DISCREPANCY` must be acknowledged before
  the transition succeeds.
- `PAYMENT_CONFIRMED` — cumulative `SupplierPayment.amount` (status =
  `CONFIRMED`) across every linked PO's invoice ≥ the sum of those invoices'
  values. Computed by walking BookingPurchaseOrder → PurchaseOrder → Invoice
  → SupplierPayment.
- `BL_ISSUED` — `BillOfLading` row exists for the booking.
- `IN_TRANSIT` — the BL's vessel has `atd` set.
- `CLEARED` — every container under the BL is `ContainerStatus.CLEARED`.
- `COMPLETE` — every container's `lifecycle_status` is `BANKED` (or
  acknowledged `DISPUTED`). Marking deliveries `DELIVERED` is required but
  alone is not enough; the customer payment leg must close too.

## Container lifecycle (derived state)

A container's end-to-end position is `Container.lifecycle_status`
(`ContainerLifecycleStatus`):

`ORDERED → AT_SEA → ARRIVED → IMPORT_CLEARED → DELIVERED → INVOICED → PAID
→ BANKED → CLOSED`, with `DISPUTED` as a side-state.

This field is **derived** from concrete events (vessel atd/ata, customs
status, delivery status, customer payment tranches vs `sale_price_total`).
Every event that could change it calls
`ContainerLifecycleService.recompute(container_id)`. The booking-level
`COMPLETE` precondition reads this field — that's how customer-paid bubbles
up to close the booking.

---

## Critical files

| Concern | Path |
|---|---|
| Entry point, CORS, router mounts, exception handlers | `app/main.py` |
| Per-resource route files (15 modules, 16 routers — `parties.py` exports broker + company) | `app/api/routes/` — auth, bl, bookings, clearing, containers, customer_payments, customs, delivery, documents, invoices, notifications, parties (brokers + companies), po, supplier_payments, vessels |
| Booking state machine — read before touching transitions | `app/services/booking_service.py` |
| Container lifecycle derivation — recompute() called by every event writer | `app/services/container_lifecycle_service.py` |
| Supplier vs Customer payment services | `app/services/supplier_payment_service.py`, `app/services/customer_payment_service.py` |
| Auth service — JWT issue, bcrypt hashing, refresh | `app/services/auth_service.py` |
| Auth guards + financial masking | `app/middleware/auth.py` |
| JWT revocation + Redis client | `app/core/redis.py` |
| Trusted-proxy IP resolution | `app/core/network.py` |
| Settings + boot-time validation | `app/core/config.py` |
| Structured JSON logging + `request_id` contextvar | `app/core/logging.py` |
| ORM models (Booking, BookingUser, BookingPurchaseOrder, Container w/ sale-side + lifecycle, Broker, Company, SupplierPayment, CustomerPayment, AuditLog, CustomsRecord, CustomsNote, VesselUpdate, DeliverySchedule, DeliveryContainer) | `app/db/models.py` |
| DB engine + session factory | `app/db/database.py` |
| Celery tasks + beat schedule | `app/background/tasks.py` |
| Storage (presigned URLs) | `app/services/storage_service.py` |
| Notification dispatch — push enqueued via Celery (`send_push_notification.delay`) | `app/services/notification_service.py` |
| PO / Invoice services | `app/services/po_service.py`, `app/services/invoice_service.py` |
| Container / Customs / Clearing / Delivery services | `app/services/container_service.py`, `customs_service.py`, `clearing_service.py`, `delivery_service.py` |
| Idempotency dependency | `app/middleware/idempotency.py` |
| Rate limiter config | `app/middleware/rate_limit.py` |
| Security headers middleware | `app/middleware/security_headers.py` |
| Request logging + `request_id` propagation | `app/middleware/request_logging.py` |
| Initial schema migration | `app/db/migrations/versions/56df7eb7f236_initial_schema.py` |
| P1 indexes + CHECK constraints | `app/db/migrations/versions/a1b2c3d4e5f6_p1_indexes_and_constraints.py` |
| P0 trading-core remediation (5 migrations, c3d4… → a7b8…) | `app/db/migrations/versions/c3d4e5f6a7b8_*.py`, `d4e5f6a7b8c9_*`, `e5f6a7b8c9d0_*`, `f6a7b8c9d0e1_*`, `a7b8c9d0e1f2_*` |
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
| Forgetting `Idempotency-Key` on `POST /invoices/{id}/supplier-payments`, `POST /purchase-orders/{id}/invoice`, or `POST /bookings/{id}/containers/{id}/customer-payments` | Returns 400. All clients must generate and send a UUID per logical request |
| Routing payments to `/bookings/{id}/payments` | That endpoint no longer exists. Supplier payments nest under `/invoices/{invoice_id}/supplier-payments`; customer payments under `/bookings/{booking_id}/containers/{container_id}/customer-payments` |
| Writing `Container.lifecycle_status` directly | Use `ContainerLifecycleService.recompute(db, container_id)` — it derives the value from inputs (vessel atd/ata, customs, delivery, customer-payment banked total) |
| Treating Shipment as a 1:1 with PO and BL | The model is `Booking ← M:N → PurchaseOrder` (via `booking_purchase_orders`), `Booking 1:1 BillOfLading`, `Invoice 1:1 PurchaseOrder`. Preconditions walk the join chain |
| Putting credentials in `.env` | `.env` is for non-secret config only. Real credentials (R2 access key + secret) live in `./secrets/<NAME>` files mounted as Docker secrets at `/run/secrets/<NAME>`. Pydantic-Settings reads them via `secrets_dir`. This keeps `docker compose config` from rendering values as plaintext |

---

## Current status & next work

**P0** — COMPLETE (PR #6, `main` at `09da227`).
**P1** — Tasks 1, 2, 3, 5 merged (HTTP resilience, Celery push, R2 end-to-end, VesselFinder polling). Task 4 (Destin8) still blocked on tier/credentials.
**P2** — COMPLETE. All 7 hardening items done as of `p2-service-layer`.
**P2.5** — RLS enabled on all 22 public tables (migration `5ab45b2e1574`, branch `p2-supabase-rls`).
**Phase B** — COMPLETE. Post-RLS correctness fixes (PR #20, `main` at `50d46a7`).
**Phase C** — COMPLETE. Hygiene sweep — bcrypt rounds setting, /ready probe timeout, CORS dedup, ShipmentMembership Protocol (PR #21).
**Phase D** — COMPLETE. `/docs` admin lockdown in production + payment-service AsyncMock fix (PRs #22 + #23, `main` at `7f3b0cd`).
**Phase H** — COMPLETE. Docker dev-stack hygiene + Docker-secrets adoption for R2 credentials (PR #24, `main` at `047ebed`).
**Trading-core remediation (P0.1–P0.5)** — COMPLETE on `p0-trading-core-refactor` (PR #28). Realigns the schema with the client's actual workflow: Booking entity, M:N Booking↔PO, supplier-vs-customer payment split, ContainerLifecycleStatus end-to-end, broker + end-company on container and delivery point. Five migrations in order: `c3d4e5f6a7b8` → `d4e5f6a7b8c9` → `e5f6a7b8c9d0` → `f6a7b8c9d0e1` → `a7b8c9d0e1f2`. 292 tests green, ruff + mypy clean.
**P3** — TODO (read cache, soft delete, TZ audit, load test; `/docs` lockdown landed early in Phase D).
**Phase G** — TODO. Replace `passlib` before any Python ≥3.13 upgrade; optional `python-jose` → `pyjwt` swap.

Full task specs (acceptance criteria, file lists, poller algorithms) live in
[`docs/ROADMAP.md`](docs/ROADMAP.md). Summary of remaining open work below.

| # | Item | Status | Blocker |
|---|---|---|---|
| P1.1 (trading) | Multi-leg ShipmentLeg (transshipment legs) | TODO | none — design ready |
| P1.2 (trading) | Booking-confirmation free-day / detention-rate fields | TODO | none |
| P1.3 (trading) | UK port-of-discharge enum + per-port templates | TODO | none |
| P1.4 (trading) | A/R aging Celery task | TODO | none |
| P1.5 (trading) | Demurrage countdown alerts | TODO | none |
| P1.6 (trading) | Outbound `CustomerInvoiceBatch` entity (replaces free-text customer_invoice_ref) | TODO | none |
| P1.4 (infra)  | Destin8 polling worker | BLOCKED | API credentials + tier choice |
| P2.x (trading) | Dispute acknowledgement flow + ops dashboard alerts | TODO | none |
| P3 | Read caching, soft delete, TZ audit, locust load test | TODO | product decisions |
| G1 | Replace `passlib` (blocks Python ≥3.13) | TODO | none |

### Open decisions (gate the blocked items)

1. Destin8 tier + endpoint URL (gates infra P1.4)
2. Data retention / GDPR policy (drives P3 soft-delete work)
3. Outbound customer invoice numbering scheme + PDF template (gates trading P1.6)

---

## GitHub

- Repo: `Adamleefeldman/parcel-track`. `main` is source of truth — always sync before branching.
- One branch + PR per roadmap task. CI runs ruff (blocking), pytest against a real
  Postgres service container (blocking), and mypy (blocking — at zero errors as of
  the Phase 1 / 2 / 3 cleanup; per-module strict overrides still TODO).
