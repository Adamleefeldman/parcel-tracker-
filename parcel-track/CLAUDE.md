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
| Per-resource route files (19 modules, 20 routers — `parties.py` exports broker + company) | `app/api/routes/` — admin, auth, bl, bookings, clearing, containers, customer_payments, customs, delivery, documents, invoices, money_risk, notifications, parties (brokers + companies), po, port_templates, shipment_legs, supplier_payments, vessels |
| Admin read endpoints — `GET /users`, `GET /invites`, `GET /audit-logs` (all `require_admin`, read-only) backing the mobile Admin tab People/System sections. View + send-invites scope only (no revoke/deactivate/role-change). `InviteOut` NEVER serialises `token_hash`; audit `actor_name` joined from `User`. Reuses existing `POST /auth/invite` for sends | `app/api/routes/admin.py`, `app/services/admin_service.py`, schemas `InviteOut`/`AuditLogOut` (users reuse `UserOut`) |
| Booking state machine — read before touching transitions | `app/services/booking_service.py` |
| Shipment-leg service (multi-leg transshipment routes) | `app/services/shipment_leg_service.py` |
| Port-template / A/R-aging / demurrage services | `app/services/port_template_service.py`, `ar_aging_service.py`, `demurrage_service.py` |
| Money-risk read endpoint — `GET /money-risk` aggregates A/R-aging buckets + demurrage countdown + dispute counts for the mobile dashboard (read-only; reuses `ARagingService.summary` + `DemurrageService.countdown`) | `app/api/routes/money_risk.py`, `app/services/money_risk_service.py`, `app/schemas/money_risk.py` |
| Container lifecycle derivation — recompute() called by every event writer | `app/services/container_lifecycle_service.py` |
| Supplier vs Customer payment services | `app/services/supplier_payment_service.py`, `app/services/customer_payment_service.py` |
| Auth service — JWT issue, bcrypt hashing, refresh | `app/services/auth_service.py` |
| Auth guards + financial masking | `app/middleware/auth.py` |
| JWT revocation + Redis client | `app/core/redis.py` |
| Trusted-proxy IP resolution | `app/core/network.py` |
| Settings + boot-time validation | `app/core/config.py` |
| Structured JSON logging + `request_id` contextvar | `app/core/logging.py` |
| ORM models (Booking w/ confirmation fields, BookingUser, BookingPurchaseOrder, Container w/ sale-side + lifecycle, Broker, Company, PortTemplate, SupplierPayment, CustomerPayment, ShipmentLeg, AuditLog, CustomsRecord, CustomsNote, VesselUpdate, DeliverySchedule, DeliveryContainer) | `app/db/models.py` |
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

### Local vs prod — the two databases, plainly

There are two completely separate databases and they never sync:

1. **Local Docker Postgres** (`parceltrack-postgres` container) — what the host
   `.env` and the local API container point at. All dev work, tests, seeding,
   and Expo Go demos read/write THIS one.
2. **Prod Supabase** — what Railway runs against. Touching it locally requires
   `uv run --env-file .env.supabase ...`, deliberately.

If "the data isn't showing up", the near-certain cause is writing to one DB
while the app reads the other. Users/logins also live per-database — an admin
created locally does not exist in prod, and vice versa.

### Secrets

Real credentials (R2 keys, etc.) are **not** in `.env`. They live as one file
per secret in `parcel-track/secrets/` (gitignored) and are mounted into
containers as Docker secrets at `/run/secrets/<NAME>`; pydantic-settings reads
them via `secrets_dir`. Never `cat` these files or echo their values — load
them into a command's environment without printing them.

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

## Demo data for manual verification

Use `scripts/seed_demo.py` (via the `/seed-demo-data` skill) — **never
hand-written INSERT statements**. Raw SQL seeding has failed six-plus times in
a row on: Postgres enum labels (`invalid input value for enum postatus:
"submitted"` — most enums store the uppercase member NAME, but
`containerlifecyclestatus`/`ukport`/`customerpaymentmethod`/`deliverytype`
store lowercase values via `lowercase_enum()`), `NOT NULL` ids on junction
tables, and uuid/text casts. The script uses the ORM models directly so none
of that can go wrong, is idempotent (keyed on `DEMO-` refs), and has a
`--reset` flag. Note: `Container.bl_id` is NOT NULL — containers can only be
seeded from `BL_ISSUED` onward.

```bash
uv run python scripts/seed_demo.py            # all scenarios
uv run python scripts/seed_demo.py --reset    # remove demo rows
```

If a verification needs a state the script can't produce, extend the script —
don't bypass it.

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
| Script "worked" but the API doesn't see the data | The host's `.env` targets local Docker Postgres; the API container targets the same. Anything pointing at prod requires `uv run --env-file .env.supabase ...`. If you used the host `.env` to target prod by accident, your changes never reached the API stack |

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
**Trading P1.1** — COMPLETE (PR #29). Additive multi-leg support: `shipment_legs` table (migration `f1a2b3c4d5e6`) + `ShipmentLegService` + `/bookings/{id}/legs` routes. `Vessel` and the VesselFinder poller untouched — legs are an ordered route-history record.
**Trading P1.2–P1.5** — COMPLETE (PR #30). P1.2: 9 booking-confirmation columns on `Booking`. P1.3: `UKPort` enum (`BillOfLading.port_of_discharge` is now typed) + `PortTemplate` per-port defaults + `/port-templates` routes; a new BL inherits port free-day defaults onto its booking. P1.4: daily `check_ar_aging` task flags delivered-but-unbanked containers. P1.5: daily `check_demurrage_countdown` task warns near free-time expiry. Migrations `b1c2d3e4f5a6` → `c2d3e4f5a6b7` → `d3e4f5a6b7c8`. P1.6 (CustomerInvoiceBatch) still TODO — blocked on the invoice-numbering decision.
**Trading P2.1** — COMPLETE on `trading-p2.1-dispute-ack`. New `Container.dispute_acknowledged_at` + `dispute_acknowledged_by` (migration `e4f5a6b7c8d9`); admin-only `PATCH /bookings/{id}/containers/{cid}/dispute` (open) and `…/dispute/acknowledge` (clear). `Booking.COMPLETE` precondition now counts acknowledged disputes as resolved — closes the dead-end that previously left disputed bookings permanently stuck. Marker model: lifecycle stays `DISPUTED` (history preserved), only the booking-completion blocker is lifted.
**Money-risk read endpoint** — COMPLETE on `money-risk-endpoints`. Additive + read-only (no migration, no model changes): `GET /api/v1/money-risk` → `MoneyRiskOut { ar_aging, demurrage, disputes }`, gated to ADMIN + UK_AGENT (same roles that receive the P1.4/P1.5 alerts). Surfaces the existing A/R-aging + demurrage computed signals as totals/breakdowns for the mobile dashboard (Phase 10). New `MoneyRiskService` composes `ARagingService.summary` + `DemurrageService.countdown` + dispute counts; the `run()` alerters are untouched. Three confirmed approximations baked in: (1) outstanding £ = **full** sum of `Container.sale_price_total` for unbanked containers (not netted against banked); (2) **whole-day** demurrage countdown (`Vessel.ata` is a `date`, so `days_remaining` is an int, negative = expired — no fabricated hour precision); (3) aging clock = `Container.updated_at` (the existing proxy; no precise `delivered_at`), buckets 0-14 / 15-30 / 31-60 / 60+. Don't "fix" these without revisiting the underlying model gaps.
**Booking-list summary fields** — COMPLETE on `booking-list-summary-fields` (backend half of mobile Phase 11). Additive read-only enrichment of `BookingOut`: `po_count`, `container_count`, `vessel_name`, `eta` (date, no time), `port_of_discharge`, `product_summary` (distinct PO product descriptions in PO-creation order, max 2 shown, then "+N more"). Names are a pinned contract with the mobile client — do not rename. Computed by `BookingService.summary_fields()` over the `BOOKING_SUMMARY_LOADER_OPTIONS` selectinload chain (no per-row lazy loads); populated on list + detail. Create/PATCH responses return the schema defaults (0 / None) — accurate for a fresh booking, list/detail are the source of truth for cards.
**Data-Foundation Phase 1A** — IN PROGRESS (pillar-by-pillar; spec `docs/DATA-FOUNDATION-SPEC.md`, plan `docs/EXECUTION-PLAN.md`).
- Pillar 1 (Currency & FX) — COMPLETE: `currencies` master + AED (#64), `fx_rates` + ExchangeRate-API feed + `FxService` (#66), money USD-capture columns on the 5 money tables (#67). Alembic `b0c1d2e3f4a5` → `c1d2e3f4a5b6` → `d1e2f3a4b5c6`.
- Pillar 2 (Legal Entity) — COMPLETE on `p1a-4-legal-entities` (migration `8944b3e39914`). `legal_entities` master + seeded default (WT Trading LLC / The FMCG Hub, `is_default`) + inline RLS; nullable indexed `legal_entity_id` FK on all six transaction tables (purchase_orders, invoices, supplier_payments, customer_payments, bookings, containers), backfilled to the default. Services stamp the default at create via `LegalEntityService.default_id`; admin CRUD at `/legal-entities` (audited by `entity_code`, like currency). NOT NULL tightening deferred to Session 5 (`p1a_11`); UAE Free-Zone watch-flag deferred to Pillar 3 (needs party jurisdictions).
- Pillar 3 (Party master) — COMPLETE on `p1a-5-party-master` (migration `206b3ce9448f`). `parties` master (suppliers + all non-customer counterparties) + child `party_bank_accounts` (per-party default bank account, auto-defaults the first) + inline RLS on both; new `PartyType` enum (supplier / freight_forwarder / haulier / warehouse_operator / customs_broker, lowercase-valued). Nullable indexed `supplier_party_id` FK on `purchase_orders` (validated to an active SUPPLIER on PO create; legacy `supplier_ref` untouched); seeded the single existing supplier SCDB (Morocco/USD) and backfilled every existing PO to it. `PartyService` (CRUD + bank accounts + free-zone watch, audited by `entity_code`); admin `/parties` routes (`GET ?type=`, `POST`, `GET /{id}`, `PATCH /{id}`, `POST /{id}/bank-accounts`) + read `GET /parties/free-zone-watch`. V1 UAE Free-Zone watch-flag: report-only, country-based, conservative (flags any UAE counterparty while a UAE Free-Zone trading entity exists; never blocks a write). Broker/Company untouched (spec §4 non-goal). NOT NULL tightening deferred to Session 5 (`p1a_11`).
- Next: Pillar 4 (Product / SKU master) — `p1a-6-8-product-master`.
**P3** — TODO (read cache, soft delete, TZ audit, load test; `/docs` lockdown landed early in Phase D).
**Phase G** — TODO. Replace `passlib` before any Python ≥3.13 upgrade; optional `python-jose` → `pyjwt` swap.

Full task specs (acceptance criteria, file lists, poller algorithms) live in
[`docs/ROADMAP.md`](docs/ROADMAP.md). Summary of remaining open work below.

| # | Item | Status | Blocker |
|---|---|---|---|
| P1.1 (trading) | Multi-leg ShipmentLeg (transshipment legs) | DONE | additive `shipment_legs` table + `/bookings/{id}/legs` routes |
| P1.2 (trading) | Booking-confirmation free-day / detention-rate fields | DONE | 9 columns on `Booking` |
| P1.3 (trading) | UK port-of-discharge enum + per-port templates | DONE | `UKPort` enum + `PortTemplate` + `/port-templates` |
| P1.4 (trading) | A/R aging Celery task | DONE | daily `check_ar_aging` |
| P1.5 (trading) | Demurrage countdown alerts | DONE | daily `check_demurrage_countdown` |
| P1.6 (trading) | Outbound `CustomerInvoiceBatch` entity (replaces free-text customer_invoice_ref) | TODO | none |
| P1.4 (infra)  | Destin8 polling worker | BLOCKED | API credentials + tier choice |
| P2.1 (trading) | Dispute acknowledgement flow | DONE | open/ack dispute routes + COMPLETE precondition counts acked as resolved |
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
