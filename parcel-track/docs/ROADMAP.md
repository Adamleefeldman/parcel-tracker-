# parcel-tracker — Implementation Roadmap

Detailed task specs for work beyond P0. CLAUDE.md carries only the high-level status
table; the file-by-file breakdowns and acceptance criteria live here.

## Status summary (as of 2026-04-27)

- **P0** — COMPLETE (PR #6, `main` at `09da227`)
- **P1** — PARTIALLY COMPLETE (Tasks 1 + 2 merged; Tasks 3–5 blocked on external accounts)
- **P2** — COMPLETE (all 7 items done; P2.18 service-layer extraction merged on `p2-service-layer`)
- **P3** — TODO

---

## P1 — External integrations + resilience

### Execution order

| # | Task | Status | External dependency |
|---|---|---|---|
| 1 | Outbound-HTTP resilience helper | TODO | none |
| 2 | Push notifications via Celery | TODO | none |
| 3 | Cloudflare R2 end-to-end | BLOCKED | CF account + bucket |
| 4 | Destin8 polling worker | BLOCKED | Destin8 API credentials + tier |
| 5 | VesselFinder polling worker | BLOCKED | VesselFinder plan + key |

**First branch:** Tasks 1 + 2 together (one PR, ~500 lines, no external accounts needed).
Land Task 1 files + tests first (green CI on helper alone), then layer Task 2 on top.

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

### Task 3 — Cloudflare R2 end-to-end (BLOCKED on CF account)

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

### Task 5 — VesselFinder polling worker (BLOCKED on plan/key)

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

## P3 — Scale prep (TODO)

| # | Item |
|---|---|
| 20 | Read caching for shipment-detail (Redis, 30s TTL, invalidate on transition) |
| 21 | Soft delete + archival (UK customs records = 6yr retention) |
| 22 | API versioning story for `/api/v2` |
| 23 | OpenAPI polish — lock `/docs` behind ADMIN in production |
| 24 | Multi-region readiness: timezone-aware datetimes everywhere |
| 25 | Load test with locust (target: p95 < 300ms at 100 concurrent users) |

---

## Open decisions (required before tasks 3–5 and P3)

1. **CF R2 account** — when will you create it? (gates Task 3)
2. **Destin8 tier + exact endpoint URL** — drives poll cadence and rate-limit budget (gates Task 4)
3. **VesselFinder plan** — free vs paid drives polling interval (gates Task 5)
4. **Notification scope for customers** — every vessel status change, or only
   `APPROACHING / DELAYED / ARRIVED`? (affects Task 5 acceptance criteria)
5. **Hosting** — Fly.io or Railway recommended (both run the Dockerfile directly,
   support api + worker + beat as three processes from one image; Postgres stays on
   Supabase, Redis on Upstash or managed)
6. **Data retention / GDPR** — drives P3 #21 soft-delete + archival policy

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
- OpenAPI page curated and locked behind admin auth in production
