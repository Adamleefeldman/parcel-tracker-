# parcel-tracker — Implementation Roadmap

Detailed task specs for work beyond P0. CLAUDE.md carries only the high-level status
table; the file-by-file breakdowns and acceptance criteria live here.

## Status summary (as of 2026-05-04)

- **P0** — COMPLETE (PR #6, `main` at `09da227`)
- **P1** — PARTIALLY COMPLETE (Tasks 1, 2, 3, 5 merged; Task 4 Destin8 still blocked on tier/credentials)
- **P2** — COMPLETE (all 7 items done; P2.18 service-layer extraction merged on `p2-service-layer`)
- **P2.5** — COMPLETE (RLS enabled on all 22 public tables, migration `5ab45b2e1574`)
- **Phase B** — COMPLETE (post-RLS correctness fixes, PR #20, `main` at `50d46a7`)
- **Phase C** — COMPLETE (hygiene sweep, PR #21)
- **Phase D** — COMPLETE (D1 docs lockdown PR #23; D2 payment-service mock fix PR #22; `main` at `7f3b0cd`)
- **Phase H** — COMPLETE (docker dev-stack hygiene + R2 secrets adoption, PR #24, `main` at `047ebed`)
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
