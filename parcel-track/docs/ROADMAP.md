# parcel-tracker — Implementation Roadmap

Detailed task specs for work beyond P0. CLAUDE.md carries only the high-level status
table; the file-by-file breakdowns and acceptance criteria live here.

## Status summary (as of 2026-05-18)

- **P0 (initial)** — COMPLETE (PR #6, `main` at `09da227`)
- **P1 (infra)** — PARTIALLY COMPLETE (Tasks 1, 2, 3, 5 merged; Task 4 Destin8 still blocked on tier/credentials)
- **P2 (hardening)** — COMPLETE (all 7 items done; P2.18 service-layer extraction merged on `p2-service-layer`)
- **P2.5** — COMPLETE (RLS enabled on all 22 public tables, migration `5ab45b2e1574`)
- **Phase B** — COMPLETE (post-RLS correctness fixes, PR #20, `main` at `50d46a7`)
- **Phase C** — COMPLETE (hygiene sweep, PR #21)
- **Phase D** — COMPLETE (D1 docs lockdown PR #23; D2 payment-service mock fix PR #22; `main` at `7f3b0cd`)
- **Phase H** — COMPLETE (docker dev-stack hygiene + R2 secrets adoption, PR #24, `main` at `047ebed`)
- **Trading-core remediation (P0.1–P0.5)** — COMPLETE on `p0-trading-core-refactor` (PR #28). See § Trading-core remediation below.
- **Trading P1** — IN PROGRESS (P1.1 multi-leg ShipmentLeg COMPLETE via PR #29; P1.2–P1.5 COMPLETE on `trading-p1.2-p1.5` — booking-confirmation fields, UK port enum + templates, A/R aging cron, demurrage alerts; P1.6 outbound CustomerInvoiceBatch still TODO, blocked on the invoice-numbering decision). See § Trading P1 below.
- **P3** — TODO
- **Phase G** — TODO (runtime upgrade prep: passlib must go before Python ≥3.13)

---

## P1 — External integrations + resilience

### Execution order

| # | Task | Status | External dependency |
|---|---|---|---|
| 1 | Outbound-HTTP resilience helper | DONE (PR #7) | none |
| 2 | Push notifications via Celery | DONE (PR #7) | none |
| 3 | Cloudflare R2 end-to-end | DONE (PR #12) | CF account + bucket |
| 4 | Destin8 polling worker | BLOCKED | Destin8 API credentials + tier |
| 5 | VesselFinder polling worker | DONE (PR #13) | VesselFinder plan + key |

Only Task 4 (Destin8) remains. Same shape as Task 5 — see spec below; gated on tier choice.

---

### Task 1 — Outbound-HTTP resilience helper

**Goal:** single async HTTP client factory used by all integrations, with timeouts,
retries + jittered backoff, typed provider exceptions, and a Redis-backed per-provider
circuit breaker.

**Files to create:**
- `app/integrations/__init__.py`
- `app/integrations/_http.py` — client factory + circuit breaker
- `app/integrations/_exceptions.py` — `IntegrationError`, `IntegrationTimeout`,
  `IntegrationUnavailable`, `IntegrationRateLimited`, `IntegrationAuthError`
- `tests/unit/test_integrations_http.py` — unit tests with `httpx.MockTransport`

**Files to modify:**
- `app/core/config.py` — add `INTEGRATION_HTTP_TIMEOUT_SECONDS: float = 10.0`,
  `INTEGRATION_HTTP_RETRIES: int = 2`,
  `INTEGRATION_CIRCUIT_BREAKER_THRESHOLD: int = 5`,
  `INTEGRATION_CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 60`
- `.env.example` — document new vars

**Acceptance criteria:**
- `build_client(provider: str) -> httpx.AsyncClient` returns a client with total timeout,
  retry transport (backoff = base × 2ⁿ + jitter), and `User-Agent: parceltrack/<ver> (<provider>)`
- Redis circuit breaker keyed `integrations:cb:<provider>` with states
  `closed / open / half-open`; opens after N failures, resets after cooldown
- Non-2xx mapped to typed exceptions: 429 → `IntegrationRateLimited` (respects
  `Retry-After`), 5xx → `IntegrationUnavailable`, timeouts → `IntegrationTimeout`
- Unit tests: successful call, retry-and-succeed, retry-exhausted, circuit-open
  short-circuits, 429 propagation, malformed JSON
- No real network calls in tests — use `httpx.MockTransport`

---

### Task 2 — Push notifications via Celery

**Goal:** move the Expo HTTP call out of the request path. Routes write the
`Notification` row synchronously; push dispatch is enqueued.

Current state: `send_push_notification` Celery task exists in `app/background/tasks.py`
but is never invoked — `NotificationService._send_push` still calls Expo synchronously
via `httpx.AsyncClient`. This task wires them together.

**Files to modify:**
- `app/services/notification_service.py`
  - Remove `_send_push` body; replace with thin wrapper that enqueues Celery task
  - In `send()`: after DB insert + commit, call `send_push_notification.delay(notification_id)`
  - Pass `notification_id` (not raw token) so the task re-reads the row
- `app/background/tasks.py`
  - Rewrite `send_push_notification` to signature `(notification_id: str)`
  - Task opens its own DB session, fetches `Notification` + `User` (for expo token),
    posts to Expo via Task 1 `_http` helper with provider `"expo"`
  - Sets `notification.push_sent = True` on success, commits
  - Uses `autoretry_for=(IntegrationTimeout, IntegrationUnavailable,)`,
    `retry_backoff=True`, `max_retries=3`
- `tests/integration/conftest.py` — add autouse fixture that swaps `.delay()` for a
  direct synchronous call under `CELERY_TASK_ALWAYS_EAGER` so existing tests still pass

**Files to review (no change expected):**
- All 9 call sites in `routes.py` that invoke `NotificationService` — public API
  is unchanged for callers

**Acceptance criteria:**
- Endpoint that fires a notification returns in <50ms (no Expo round-trip in request path)
- `notification.push_sent == True` after task runs (verified by existing tests under eager mode)
- Task retries on Expo 5xx; gives up silently on 4xx (invalid token)
- No breaking change to `NotificationService.send()` public signature

---

### Task 3 — Cloudflare R2 end-to-end (DONE — PR #12, `718d5ee`)

**Operational steps (your work):**
- Create Cloudflare account + R2 bucket `parceltrack-documents`
- Create R2 API token scoped to that bucket (Object Read & Write)
- Configure bucket CORS to allow presigned PUT from mobile app origins
- Set retention/lifecycle: customs docs 6 years, everything else 2 years
- Populate `.env` and hosting platform secrets with `STORAGE_*` values

**Code changes:**
- `app/services/storage_service.py` — add explicit
  `botocore.Config(signature_version="s3v4", s3={"addressing_style": "virtual"})`;
  add `verify_upload(file_key) -> dict` that calls `head_object()` and returns
  `{size, etag, content_type}` or raises `StorageObjectNotFound`
- `app/api/routes/routes.py` — `POST /documents/confirm`: call
  `StorageService.verify_upload(file_key)` before inserting `Document` row;
  reject with 400 if missing, 413 if exceeds `MAX_FILE_SIZE_BYTES` (currently 50 MB)
- `app/core/exceptions.py` — add `StorageObjectNotFound` mapping to 400
- `tests/integration/conftest.py` — extend autouse mock to cover `verify_upload`
  (currently mocks `generate_file_key`, `get_upload_url`, `get_download_url`)
- `README.md` — add "Cloudflare R2 setup" section
- `scripts/smoke_r2.py` — new script: reads `.env`, calls upload-url → curl PUT →
  confirm → download-url → curl GET; exits 0 on round-trip success

**Acceptance criteria:**
- `python scripts/smoke_r2.py` completes a full round-trip against a real R2 bucket
- Confirm endpoint rejects a `file_key` that was never PUT
- No existing test breaks

---

### Task 4 — Destin8 polling worker (BLOCKED on credentials + tier decision)

**Decision required:** which Destin8 endpoints and tier? Drives poll cadence, retry
budget, and rate-limit self-imposition.

**Files to create:**
- `app/integrations/destin8/__init__.py`
- `app/integrations/destin8/client.py` — `Destin8Client.get_container_status(ref)`
- `app/integrations/destin8/mapping.py` — explicit `DESTIN8_TO_PORT_STATUS` lookup;
  unknown values raise `UnmappedDestin8Status` (logged, skipped — no silent guessing)
- `app/integrations/destin8/poller.py` — `poll_destin8_containers(db)` orchestrator
- `tests/unit/test_destin8_mapping.py`
- `tests/integration/test_destin8_poller.py` — cassette-based (pytest-recording)

**Files to modify:**
- `app/core/config.py` — add `DESTIN8_BASE_URL`, `DESTIN8_API_KEY`,
  `DESTIN8_POLL_INTERVAL_MINUTES: int = 15`, `DESTIN8_ENABLED: bool = False`
- `app/background/tasks.py` — new `poll_destin8_containers_task` in `beat_schedule`;
  returns immediately if `DESTIN8_ENABLED` is false
- `.env.example`, `pyproject.toml` (add `pytest-recording` to `[dependency-groups] dev`)

**Poller algorithm (single iteration):**
1. Query containers where `destin8_ref IS NOT NULL AND port_status != RELEASED`
   and `bl.vessel.status IN (DEPARTED, ETD_SET)` — LIMIT 100 per iteration
2. Call `Destin8Client.get_container_status(ref)` under circuit breaker; skip on
   `IntegrationUnavailable / IntegrationTimeout` (next tick retries)
3. On status change: update `container.port_status`, write `AuditLog`
   (`action="container.port_status_changed"`, `source="destin8"`),
   notify UK_AGENT + ADMIN via `NotificationService`

---

### Task 5 — VesselFinder polling worker (DONE — PR #13, `fc95515`)

**Decision required:** free tier ≈ 1 update per vessel per few hours; paid = finer
granularity. Drives `VESSELFINDER_POLL_INTERVAL_MINUTES` default.

Same shape as Task 4. Key differences:

**Config additions:** `VESSELFINDER_BASE_URL`, `VESSELFINDER_API_KEY`,
`VESSELFINDER_POLL_INTERVAL_MINUTES: int = 30`,
`VESSELFINDER_ETA_CHANGE_THRESHOLD_HOURS: int = 2`,
`VESSELFINDER_ENABLED: bool = False`

**Poller algorithm:**
1. Query `Vessel` where `status IN (DEPARTED, ETD_SET)` and most recent
   `VesselUpdate.created_at < now() - interval`
2. Always append a new `VesselUpdate` row (append-only log)
3. Only write to `Vessel.eta` if change exceeds `VESSELFINDER_ETA_CHANGE_THRESHOLD_HOURS`
4. Notify ADMIN + CUSTOMER only on `APPROACHING / ARRIVED / DELAYED` status
   transitions — not every tick (avoids push spam)

---

## Phase B — Post-RLS correctness fixes (COMPLETE — PR #20)

Four medium-severity issues surfaced by the post-RLS code review, merged as one batch.

| Item | Fix | Files |
|---|---|---|
| B1 — IMO case normalization | `.lower()` on both sides of VesselFinder IMO lookup | `app/services/vessel_poll_service.py` |
| B2 — Clearing deadline window | `timedelta(hours=48)` → `timedelta(days=2)` to match `Vessel.eta` `Date` granularity; updated docstring + notification copy | `app/background/tasks.py`, `app/services/notification_service.py` |
| B3 — MIME verification | `verify_upload` now accepts `expected_content_type` and raises `StorageMimeMismatch` on mismatch; confirm handler drops client-claim fallback | `app/services/storage_service.py`, `app/api/routes/documents.py` |
| B4 — RLS downgrade guard | `downgrade()` raises `RuntimeError` unless `ALLOW_RLS_DOWNGRADE=1` is set | `app/db/migrations/versions/5ab45b2e1574_enable_rls_on_public_tables.py` |

Test count after Phase B: **272 passed** (+6 new tests).

---

## P2 — Production hardening (COMPLETE)

| # | Item | Status | Notes |
|---|---|---|---|
| 13a | Structured logging + `request_id` | DONE | `app/core/logging.py`, JSON in prod, `X-Request-ID` header |
| 13b | Sentry | DONE | `954728d` — api + celery integrations |
| 13c | Prometheus `/metrics` | DONE | `954728d` — `prometheus-fastapi-instrumentator` |
| 14 | Idempotency keys | DONE | `0e4ef44` — Redis-backed on payments / invoices / customs notes / delivery schedule + status |
| 15 | DB indexes + CHECK constraints | DONE | `a1b2c3d4e5f6` migration — compound indexes + CHECK constraints on all numeric fields |
| 16 | Login lockout (per-account Redis counter) | DONE | `954728d` — 6-attempt / 15-min window, tested in `tests/unit/test_auth_lockout.py` |
| 17 | Split `routes.py` into per-resource modules | DONE | `ad49a36` — 13 per-resource route files under `app/api/routes/` |
| 18 | Service layer for PO / Invoice / Payment / Container / Customs / Clearing / Delivery | DONE | 7 new services under `app/services/`; all mutation logic extracted from route handlers |
| 19 | Unit tests for pure code | DONE | `tests/unit/` — security, state-machine, integrations HTTP, auth lockout, invoice variance, clearing status, payment threshold, customs cascade, delivery cascade |

---

## Phase D — Operational / security quick wins (COMPLETE — PRs #22, #23)

| Item | Fix | Files |
|---|---|---|
| D1 — Lock `/docs` behind admin in prod | Mount `/docs`, `/redoc`, `/openapi.json` under a `docs_guard` dep that enforces admin role only when `settings.is_production`. Built-in URLs disabled. | `app/main.py`, `tests/integration/test_docs_lockdown.py` |
| D2 — Fix `test_payment_service.py` AsyncMock misuse | `db = AsyncMock()` made `db.add()` return an unawaited coroutine — real SQLAlchemy `AsyncSession.add` is sync. Replaced with `db = MagicMock()` + targeted `AsyncMock` on `execute`/`flush`. Eliminated the 3 `RuntimeWarning`s that the post-D1 audit surfaced. | `tests/unit/test_payment_service.py` |

---

## Phase H — Docker / dev-stack hygiene (COMPLETE — PR #24)

Surfaced by the post-D1 docker setup audit. The image `parceltrack:dev`
hadn't been rebuilt since `2026-04-10`, the running stack was missing
`api`/`worker`/`beat`, and `docker compose config` rendered `.env`
contents in cleartext, making credential exposure during routine
debugging an easy mistake. The fix layered two coherent commits; R2
credentials migrated to file-backed Docker secrets and existing keys
were rotated as a precaution.

| Item | Fix | Files |
|---|---|---|
| H1 — `.dockerignore` typo | Removed stray `{app` copy-paste artefact (line 56). | `.dockerignore` |
| H2 — Compose env-shadowing footgun | `environment:` shadowed `env_file:`, so `STORAGE_*` from `.env` was silently ignored. Dropped the inline `STORAGE_*` keys; added an anchored `env_file: .env` (required:false) to api/worker/beat. Header comment rewritten to describe real precedence. Side benefit: 11 settings no longer enumerated in compose now flow from `.env` (INTEGRATION_*, VESSELFINDER_*, BCRYPT_ROUNDS, TRUSTED_PROXIES, SENTRY_*). | `docker-compose.yml` |
| H3 — Beat volume permission | Beat crash-looped under the non-root `app` user with "Permission denied: /var/lib/celery/celerybeat-schedule". Pre-create the directory with `app:app` ownership in the runtime stage so the named volume inherits write perms on first attach. | `Dockerfile` |
| H4 — Docker secrets for R2 credentials | `Settings.Config.secrets_dir = "/run/secrets"` so Pydantic-Settings reads file-backed secrets (env var → secrets file → default). Compose declares top-level `secrets:` with `file: ./secrets/<NAME>` refs; service-level refs use `target: <NAME>` so files land at `/run/secrets/<NAME>` matching field names. New `secrets/` dir is gitignored + dockerignored; only `.gitkeep` and `README.md` are tracked. `STORAGE_*_KEY` removed from `.env`. Production validator refuses to boot with empty values and points at the secret path in the error. After the fix, `docker compose config` no longer renders the secret values — only `source:` / `target:` references. | `app/core/config.py`, `docker-compose.yml`, `secrets/.gitkeep`, `secrets/README.md`, `.gitignore`, `.dockerignore`, `CLAUDE.md` |

End-to-end verified: stack rebuilt clean, alembic at head, `/health` and
`/ready` 200, `scripts/smoke_r2.py` round-trips 34 bytes against R2. Production
deploys (Fly.io / Railway / k8s) get the same `/run/secrets/<NAME>`
contract from their native secret managers, so no app code changes
between dev and prod.

---

## P3 — Scale prep (TODO)

| # | Item |
|---|---|
| 20 | Read caching for shipment-detail (Redis, 30s TTL, invalidate on transition) |
| 21 | Soft delete + archival (UK customs records = 6yr retention) |
| 22 | API versioning prefix `/api/v1` (DONE — all routers mount under `PREFIX` in `app/main.py`; `/v2` deferred until a real breaking change) |
| 23 | OpenAPI polish — lock `/docs` behind ADMIN in production (DONE in Phase D1) |
| 24 | Multi-region readiness: timezone-aware datetimes everywhere |
| 25 | Load test with locust (target: p95 < 300ms at 100 concurrent users) |

---

## Phase G — Runtime upgrade prep (TODO)

Surfaced by the post-D1 warnings review. Not urgent today (we ship Python 3.12),
but each item below blocks a future runtime bump and should land before then.

### G1. Replace `passlib` before Python ≥3.13

`passlib` imports the stdlib `crypt` module
(`/passlib/utils/__init__.py:854`); `crypt` is removed in Python 3.13. Passlib
itself is effectively unmaintained (last release 2020). Today's tests show one
`DeprecationWarning` per process; on Python 3.13+ the import fails outright,
which would make the api fail to boot.

**Migration plan:**
- `app/core/security.py` — replace `passlib.context.CryptContext` with direct
  `bcrypt` library calls (`bcrypt.hashpw` / `bcrypt.checkpw`). `bcrypt` is
  already a transitive dependency.
- Keep cost factor wired to `settings.BCRYPT_ROUNDS` (no behaviour change).
- Existing bcrypt hashes in the DB are byte-for-byte compatible — no data
  migration needed.
- `pyproject.toml` — drop `passlib`; promote `bcrypt` to a direct dependency.
- Re-run `tests/unit/test_security.py` and `tests/unit/test_auth_lockout.py`
  to prove old-format hashes still verify.

**Acceptance:**
- No passlib import remains under `app/`.
- Full suite green; passlib `DeprecationWarning` no longer appears in the
  warnings summary.
- Smoke: log in a user whose hash was generated by the old passlib code path.

**Note on `python-jose`:** the `datetime.utcnow()` warnings under F2 mostly
come from `python-jose`, which is also lightly maintained. Consider folding a
`python-jose` → `pyjwt` swap into F2 or into G2; the two libraries cover the
same surface for HS256 + RS256.

---

## Open decisions (required before remaining work)

1. **Destin8 tier + exact endpoint URL** — drives poll cadence and rate-limit budget (gates Task 4)
2. **Data retention / GDPR** — drives P3 #21 soft-delete + archival policy

Resolved: CF R2 account (Task 3 done); VesselFinder plan + customer notification scope
(Task 5 done — only `APPROACHING / DELAYED / ARRIVED` transitions notify); Hosting
(Railway — api + worker + beat from single Dockerfile, Postgres on Supabase, Redis on Upstash).

---

## Verification checklist (per phase)

**P1 done when:**
- `uv run pytest tests/` green (unit + integration)
- `uv run ruff check app tests` + `uv run ruff format --check` clean
- CI green on the resulting PR
- Feature flags default-off → existing behaviour unchanged in dev/test
- `python scripts/smoke_r2.py` completes a full R2 round-trip (Task 3)
- One Destin8 poll cycle flips a seeded container's `port_status` end-to-end (Task 4)
- One VesselFinder poll cycle appends a `VesselUpdate` row (Task 5)
- Notification endpoint returns in <50ms (Task 2)

**P2 done when:**
- Sentry receives a deliberate test exception from both api and worker
- `/metrics` exposes counters
- Structured JSON logs already appear with `request_id` ✅ (done)
- Replaying the same `POST /payments` with the same idempotency key returns cached
  response ✅ (done for payments/invoices; needs extension)
- `routes.py` and `schemas.py` split into per-resource files; all tests still pass
- `EXPLAIN` on shipment-detail uses the P1 compound indexes ✅ (indexes exist)
- Login lockout: 6th failed attempt in a 15-min window returns 429 regardless of password

**P3 done when:**
- Load test: 100 concurrent users on shipment-list + shipment-detail, p95 < 300ms
- OpenAPI page curated and locked behind admin auth in production ✅ (Phase D1, PR #23)

---

## Trading-core remediation (P0.1–P0.5) — COMPLETE on `p0-trading-core-refactor` (PR #28)

Deep-dive analysis of the client's `FMCG HUB – COMPLETE TRADING TRACKER 2026-2.xlsx`
plus supporting POs / PFIs / commercial invoices / booking confirmations / SWBs /
declarations / FF invoices surfaced five load-bearing gaps in the original schema.
This branch fixes them. Client (WT Trading LLC, trading as The FMCG Hub) had not
yet onboarded, so breaking migrations were on the table.

| Tier | Goal | Migration | Key entities / routes |
|---|---|---|---|
| P0.1 | Decouple `PurchaseOrder` from `Shipment`; introduce `Booking` | `c3d4e5f6a7b8` | `bookings`, `booking_users`, `booking_purchase_orders` junction; `Invoice.purchase_order_id`; `/bookings/*`, `/bookings/{id}/purchase-orders`, `/purchase-orders/{id}/invoice` |
| P0.2 | Container as the operational unit (sale-side fields, broker, end-company) | `d4e5f6a7b8c9` | `Broker`, `Company`; container `delivery_type`, `sale_price_*`, `broker_id`, `end_company_id`, `sale_currency`; `/brokers`, `/companies`, `PATCH /containers/{id}/sale` |
| P0.3 | Split `Payment` into `SupplierPayment` (per-Invoice, USD) + `CustomerPayment` (per-Container, GBP, multi-tranche, cash/transfer, variance, courier+bank charges, banked_total) | `e5f6a7b8c9d0` | `supplier_payments`, `customer_payments`; `CustomerPaymentMethod`; `/invoices/{id}/supplier-payments`, `/bookings/{id}/containers/{id}/customer-payments` |
| P0.4 | Customer-paid lifecycle. `ContainerLifecycleStatus` derived from concrete events; booking `COMPLETE` requires every container `BANKED` | `f6a7b8c9d0e1` | `ContainerLifecycleStatus`; `Container.lifecycle_status`, `dispute_reason`, `disputed_at`; `Vessel.ata`; `ContainerLifecycleService.recompute()` wired into vessel-depart, vessel-arrived, customs-cleared, delivery-delivered, customer-payment-add |
| P0.5 | `DeliveryPoint` gains broker, end-company, delivery-type, warehouse fields | `a7b8c9d0e1f2` | `DeliveryPoint.{broker_id, end_company_id, delivery_type, warehouse_name, rebundled_at_warehouse}`; legacy `customer_user_id` kept nullable |

**Architectural shifts that downstream code must respect:**

1. **One Booking, many POs.** All booking-level preconditions walk `BookingPurchaseOrder
   → PurchaseOrder → Invoice`. There is no longer a `shipment_id` on PO / Invoice / BL —
   it's `booking_id` (BL, ClearingDocs, DeliveryPoint, Notification, AuditLog) or `purchase_order_id`
   (Invoice).
2. **Container is the addressable unit.** Sale price, broker, end-company, lifecycle
   state and customer payment live on `Container`. Cross-cutting reads should eager-load
   `Container.broker` + `Container.end_company` with explicit `selectinload`.
3. **`Container.lifecycle_status` is derived, not pushed.** Always call
   `ContainerLifecycleService.recompute()` after any event that could shift it. The
   list of writers is exhaustive today: vessel depart/arrive (`app/api/routes/vessels.py`),
   customs cleared (`app/services/customs_service.py`), delivery delivered
   (`app/services/delivery_service.py`), customer payment add
   (`app/services/customer_payment_service.py`).
4. **Booking `COMPLETE` = every container `BANKED`.** Marking deliveries delivered no
   longer auto-completes a booking. The customer payment leg must close (sum of
   `CustomerPayment.banked_total` for that container ≥ `Container.sale_price_total`).
5. **Two payment directions.** Never write a generic Payment — pick `SupplierPayment`
   (per Invoice, USD outbound) or `CustomerPayment` (per Container, GBP inbound).

**Verification snapshot at merge:**
- 292/292 tests passing (unit + integration)
- `ruff check app/ tests/` — clean
- `ruff format` — 103 files clean
- `mypy app/` — 72 files, 0 errors

**Intentionally deferred from this train** (live in Trading P1 below): multi-leg
shipment legs, demurrage / free-day fields, UK port enum, A/R aging cron,
outbound `CustomerInvoiceBatch` entity, mixed-at-warehouse pallet rebundling.

---

## Trading P1 — follow-up work surfaced by the trading-core remediation

These are the items the deep-dive plan flagged as P1 (important, but not
load-bearing for client onboarding). Each is independently shippable; pick by
business pressure.

### Trading P1.1 — Multi-leg `ShipmentLeg` — COMPLETE (`trading-p1.1-shipment-legs`)

Real Maersk routes transship (e.g. Casa → Algeciras on MAERSK NEWARK V602E,
then Algeciras → London Gateway on MADRID MAERSK V601W). `Vessel` is 1:1 with
`BillOfLading` and only carries one leg's data.

**Delivered (additive):**
- New `ShipmentLeg` model + `shipment_legs` table (migration `f1a2b3c4d5e6`):
  `id, booking_id, leg_index, vessel_name, imo_number, voyage_number,
  shipping_line, port_from, port_to, etd, atd, eta, ata` + audit timestamps;
  unique `(booking_id, leg_index)`, CHECK `leg_index >= 1`, RLS enabled.
- `Booking.legs: list[ShipmentLeg]` ordered by `leg_index`.
- `ShipmentLegService` (add / update / list) — auto-assigns `leg_index`, writes
  an `AuditLog` row per create/update.
- Routes: `POST/GET/PATCH /bookings/{id}/legs` (`shipment_legs.py`); legs surface
  in the `GET /bookings/{id}` detail response.

**Scope decision:** `Vessel`, `VesselPollService`, the Celery beat schedule,
and `ContainerLifecycleService` are **untouched** — lifecycle + AIS polling
stay on the 1:1 `Vessel` (the final, UK-arriving leg). `ShipmentLeg` is an
ordered route-history record. Unifying `Vessel` into `ShipmentLeg` (and
leg-by-leg polling) is deferred to a future phase.

### Trading P1.2 — Booking-confirmation fields — COMPLETE (`trading-p1.2-p1.5`)

9 nullable columns added to `Booking` (migration `b1c2d3e4f5a6`):
`gate_in_cutoff`, `empty_pickup_release`, `empty_return_deadline`,
`free_days_detention`, `free_days_demurrage`, `detention_rate_gbp_after`,
`demurrage_rate_gbp_after`, `port_of_discharge_terminal`, `service_mode`.
Populated via `PATCH /bookings/{id}`; surfaced on the booking detail response.

### Trading P1.3 — UK port-of-discharge enum + PortTemplate — COMPLETE (`trading-p1.2-p1.5`)

- `UKPort` enum (`FELIXSTOWE`, `LONDON_GATEWAY`, `TILBURY`, `SOUTHAMPTON`,
  `LIVERPOOL`, `OTHER`); `BillOfLading.port_of_discharge` converted free-text →
  enum (migration `c2d3e4f5a6b7`). `Vessel.port_of_discharge` left as String
  (feeds the VesselFinder UNLOCODE lookup).
- `PortTemplate` table (one row per port) carrying default free-days + rates;
  `/port-templates` routes (admin upsert, member list). When a BL is created
  with a port, the parent booking inherits the template's defaults for any
  unset P1.2 fields.

### Trading P1.4 — A/R aging Celery task — COMPLETE (`trading-p1.2-p1.5`)

Daily `check_ar_aging` task → `ARagingService`: scans containers where
`lifecycle_status` ∈ {`DELIVERED`, `INVOICED`, `PAID`} and
`updated_at < now() - AR_AGING_THRESHOLD_DAYS` (default 14); notifies
`ADMIN` + `UK_AGENT`, deduplicated once per container per week via Redis.
`AR_AGING_ENABLED` kill switch.

### Trading P1.5 — Demurrage countdown alerts — COMPLETE (`trading-p1.2-p1.5`)

Daily `check_demurrage_countdown` task → `DemurrageService`: for each arrived
vessel (`Vessel.ata` set) on a non-COMPLETE booking, computes days of free
demurrage left (`Booking.free_days_demurrage` or `DEMURRAGE_DEFAULT_FREE_DAYS`);
within `DEMURRAGE_WARNING_LEAD_DAYS` of expiry fires `NotificationType.DEMURRAGE_WARNING`
to `ADMIN` + `UK_AGENT`, deduplicated once per booking per day. New
`notificationtype` enum values added in migration `d3e4f5a6b7c8`.

### Money-risk read endpoint — COMPLETE (`money-risk-endpoints`)

Surfaces the P1.4 (A/R aging) and P1.5 (demurrage) computed signals — which
previously existed only as write-only Celery alerters — as a read endpoint for
the mobile Money-risk dashboard (mobile Phase 10). Additive + read-only: **no
migration, no model changes.** `GET /api/v1/money-risk` →
`MoneyRiskOut { ar_aging, demurrage, disputes }`, gated to `ADMIN` + `UK_AGENT`.
`MoneyRiskService.summary()` composes `ARagingService.summary()` (A/R buckets +
full unbanked exposure) + `DemurrageService.countdown()` (per-container
whole-day countdown) + dispute counts; the existing `run()` alerters are left
untouched. Three deliberate approximations carried over from the underlying
model: outstanding £ is the **full** sum of `Container.sale_price_total` (not
netted against banked tranches); demurrage `days_remaining` is whole-day
(`Vessel.ata` is a `date`; negative = expired); aging is measured from
`Container.updated_at` (no precise `delivered_at` yet), buckets 0-14 / 15-30 /
31-60 / 60+. A precise `delivered_at` / arrival-time field and dashboard write
actions (chase / escalate) are out of scope here.

### Admin People/System read endpoints — COMPLETE (`admin-people-system-reads`)

Surfaces the existing `User`, `InviteToken`, and `AuditLog` data as admin-only
read endpoints for the mobile Admin tab's **PEOPLE** + **SYSTEM** sections
(mobile Phase 13b). Additive + read-only: **no migration, no model changes.**
Three endpoints, all `require_admin`:

- `GET /api/v1/users` → `PaginatedResponse[UserOut]` — optional `role` /
  `is_active` filters; newest first. Role-breakdown counts computed client-side.
- `GET /api/v1/invites` → `PaginatedResponse[InviteOut]` — `status` ∈
  `pending|used|expired|all` (default `pending` = not used AND `expires_at > now`);
  newest first. **`token_hash` is NEVER serialised.** `expired` is a derived flag.
- `GET /api/v1/audit-logs` → `PaginatedResponse[AuditLogOut]` — global feed,
  newest first, optional `booking_id` / `actor_id` filters. `actor_name` joined
  from `User` via an explicit join (no lazy load). `old_value` / `new_value` are
  stored JSON strings, passed through verbatim.

`AdminService` holds the three read methods; the existing
`AuthService.create_invite` (`POST /auth/invite`) remains the only invite-write
path — mobile sends invites through it. **Scope: view + send-invites only.**
Revoke-invite, deactivate-user, and change-role mutations are deliberately
deferred (security-sensitive; a later phase if the client wants them).

### Trading P1.6 — Outbound `CustomerInvoiceBatch`

`CustomerPayment.customer_invoice_ref` is a free-text string today. Promote it
to a real entity so multiple containers can share one outbound invoice
(matches the spreadsheet's `INV-2603-61` covering four containers).

**New entity:**
- `CustomerInvoiceBatch(id, invoice_number unique, issued_at, total_gbp, customer_id)`
- `CustomerInvoiceBatchContainer(batch_id, container_id)` junction
- Replace `CustomerPayment.customer_invoice_ref: str` with FK
  `customer_invoice_batch_id` (nullable until issued)

PDF generation, outbound delivery, GDPR retention — all deferred to Trading P2.

### Trading P2.1 — Dispute acknowledgement flow — COMPLETE (`trading-p2.1-dispute-ack`)

Closes the dispute dead-end: previously any `Container.lifecycle_status = DISPUTED`
permanently blocked `Booking.COMPLETE` with no resolution path.

**Delivered (marker model, no eraser):**
- Two new `Container` columns: `dispute_acknowledged_at`,
  `dispute_acknowledged_by` (migration `e4f5a6b7c8d9`). `dispute_reason` /
  `disputed_at` are preserved — the dispute history stays visible.
- `PATCH /bookings/{booking_id}/containers/{container_id}/dispute` (admin) —
  sets `dispute_reason` + `disputed_at`, triggers `recompute()` to move
  lifecycle to `DISPUTED`, clears any prior ack (re-opening is supported).
- `PATCH …/dispute/acknowledge` (admin) — sets the ack timestamp + actor;
  rejects (400) if the container isn't currently `DISPUTED`. Lifecycle stays
  `DISPUTED` deliberately (history).
- `BookingService._check_preconditions` for `COMPLETE`: containers whose
  lifecycle is `DISPUTED` *and* `dispute_acknowledged_at IS NOT NULL` count
  as resolved; only unacknowledged disputes block.
- AuditLog rows for both open + acknowledge.

### Trading P2.2 — Mixed-at-warehouse pallet rebundling

Spreadsheet notes like `MIXED AT W/H 7/7/7` mean pallets get re-allocated across
containers at the UK warehouse. Adds a `PalletMovement` event log on top of P0 data.
Only worth doing once warehouse activity becomes high-volume.

### Trading P3 — Deferred (revisit before scale)

- **PO numbering canonicalisation** (`PO-2026-01` vs `PO-011`) — `po_number_normalised` shadow column + index
- **Read-side container aggregate cache** — denormalise `lifecycle_status` + aging + £-banked for the dashboard list view (premature today)
- **Multi-currency FX** — separate amount + currency + fx_rate_to_usd columns; defer until USD/GBP/EUR/MAD/AED reconciliation becomes a real blocker
- **Investor ledger module** — its own subsystem; modelled after the trading tracker's `CapitalLedgerEntry` rather than shoehorned into trading state machine
