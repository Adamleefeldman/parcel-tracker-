# Execution Plan — Data Foundation → Trading P1.6 → P3

**Purpose:** session-by-session plan for Claude Code. Each session = one branch = one green PR.
Paste the session prompt verbatim into Claude Code from the repo root (`parcel-track/`).
Companion docs: `docs/DATA-FOUNDATION-SPEC.md` (schemas), `docs/ROADMAP.md` (acceptance criteria), `CLAUDE.md` (conventions — always in force).

**Current state (2026-07-04):** Pillar 1a merged (`p1a-1-currency-master-and-aed`), Pillar 1b implemented + verified on `p1a-2-fx-rates` (459 tests green) but **not yet committed/PR'd**. Alembic head: `c1d2e3f4a5b6`.

---

## Decisions locked (do not re-litigate mid-session)

| Decision | Choice | Rationale |
|---|---|---|
| Currency model depth (spec §10.1) | Enum stays; `currencies` table for new columns | 6-table enum→FK conversion is risk with no near-term payoff; converge later once proven |
| Party scope (§10.2) | Unified `Party` master, all partner types | Same cost as supplier-only; partner portal scopes against it |
| Multi-SKU rollout (§10.3) | Full: `purchase_order_lines` + `container_contents` in 1A | Additive; UI can lag; unblocks customer-portal stock view |
| Pillar ownership (§10.4) | Single owner (Adam + Claude Code) | No second team |
| Invoice numbering (P1.6) | `INV-YYMM-seq` (e.g. `INV-2607-01`), DB-unique, gap-tolerant | Continuity with client spreadsheet (`INV-2603-61`) |
| Soft-delete retention (P3) | Customs/clearing docs 6 yr, everything else 2 yr — **confirm with client before Session 7 ships** | Matches existing R2 lifecycle policy |

**Open items that gate nothing here:** Destin8 (still blocked on tier/credentials — excluded). ExchangeRate-API key: create free key + Docker secret before Session 1 ships, so `poll_fx_rates` can go live and 1c backfill has real rates (`EXCHANGERATE_API_ENABLED=true`).

---

## Standing preamble (paste at the top of EVERY session prompt)

> Read CLAUDE.md fully. Read docs/DATA-FOUNDATION-SPEC.md §0 (design principles) and §7 (acceptance checklist) — every table/column must satisfy §7. Work on a fresh branch off latest `main` (sync first). Use subagents for exploration to keep context clean. Plan before writing code; show me the plan for approval before implementing.
>
> Verification gate before EVERY commit — all must pass, no exceptions:
> `uv run ruff check app/ tests/` · `uv run ruff format --check app/ tests/` · `uv run mypy app/` · `uv run pytest tests/ -q` · migration round-trip on real Postgres (`upgrade → downgrade -1 → re-upgrade`).
> Generate migrations with `uv run alembic revision -m "…"` — never hand-author revision hashes.
> Finish by updating CLAUDE.md "Current status" + docs/ROADMAP.md, then open a PR with a summary of scope, migrations, and test delta.

---

## Session 0 — Land Pillar 1b (15 min, do first)

**Branch:** `p1a-2-fx-rates` (exists) → PR → merge.

**Prompt:**
> Standing preamble applies. On branch `p1a-2-fx-rates`: re-run the full verification gate, then commit the Pillar 1b work (fx_rates + ExchangeRate-API client + FxService + poller + routes, per tasks/todo.md) and open the PR. No new code unless verification fails.

**Done when:** PR merged, CI green, `main` head advanced.

---

## Session 1 — Pillar 1c: money-USD capture (`p1a_3`)

**Branch:** `p1a-3-money-usd-capture` · **Spec:** §2.4

**Scope:**
- Migration `p1a_3_money_usd_capture`: nullable `fx_rate_to_usd Numeric(18,8)` + `amount_usd Numeric(14,2)` on `PurchaseOrder.total_value`, `Invoice.value`, `SupplierPayment.amount`, `CustomerPayment.amount_received`, `Container.sale_price_total` rows.
- Service rule (§2.4): every money-row create locks the live rate via `FxService.rate_to_usd()` and stores frozen `fx_rate_to_usd` + computed `amount_usd`. If no rate available → both stay null, log a warning (never block the write, never re-convert later).
- Wire into: `po_service`, `invoice` creation, `supplier_payment_service` (or equivalent), `customer_payment_service`, container sale PATCH.
- Backfill script: populate from `fx_rates` at transaction date where a rate exists; else leave null and report count.

**Acceptance:** creating each of the 5 money rows with a known rate stores locked rate + USD amount; with no rate stores nulls + warning; existing tests unchanged; new unit tests for the locking rule incl. Decimal precision (no floats).

**Prompt:**
> Standing preamble applies. Implement Data-Foundation Pillar 1c exactly per docs/DATA-FOUNDATION-SPEC.md §2.4 and docs/EXECUTION-PLAN.md Session 1. Reports must read `amount_usd`, never re-convert. Include the backfill script under `scripts/` and run it against local Docker Postgres.

---

## Session 2 — Pillar 2: legal entities (`p1a_4`)

**Branch:** `p1a-4-legal-entities` · **Spec:** §3

**Scope:** `legal_entities` table + seed default (WT Trading LLC / The FMCG Hub, `is_default=true`); nullable indexed `legal_entity_id` FK on `PurchaseOrder`, `Invoice`, `SupplierPayment`, `CustomerPayment`, `Booking`, `Container`; backfill all rows to default entity; services set it on create (default entity unless specified); `legal_entity_service.py` + admin CRUD routes (§8); UAE-domestic Free-Zone watch-flag as a report surface (boolean/notes — not enforcement).

**Acceptance:** all existing rows backfilled; new rows always tagged; RLS note — table gets RLS in Session 5's sweep, but add `ENABLE ROW LEVEL SECURITY` inline in this migration anyway (belt and braces per spec §0.4).

---

## Session 3 — Pillar 3: party master (`p1a_5`)

**Branch:** `p1a-5-party-master` · **Spec:** §4

**Scope:** `parties` + `party_bank_accounts` per spec schemas; `PartyType` enum (supplier / freight_forwarder / haulier / warehouse_operator / customs_broker); nullable `supplier_party_id` on `PurchaseOrder` (keep `supplier_ref` as legacy); backfill SCDB → one Party row; `party_service.py` + routes (`GET /parties?type=`, POST, PATCH, `POST /{id}/bank-accounts`); **do NOT touch `Broker`/`Company`** (spec §4 non-goal — they power the tested customer-payment flow).

**Acceptance:** SCDB backfilled and linked from existing POs; bank-account child rows CRUD; inline RLS; audit rows on all master writes.

---

## Session 4 — Pillar 4: product/SKU (`p1a_6` → `p1a_8`) — biggest session

**Branch:** `p1a-6-8-product-master` · **Spec:** §5 (three migrations, one branch/PR)

**Scope:**
- `p1a_6_product_master`: `product_categories`, `products` (FH-XXX-XXX `our_code`), `supplier_products` (dual-code mapping), `pack_specs`.
- `p1a_7_po_lines`: `purchase_order_lines`; `product_description` stays legacy/derived; optional seed of `products` from distinct descriptions + one line per existing PO.
- `p1a_8_container_contents`: `container_contents` (SKU mix per container).
- `product_service.py` including the **supplier-code → product resolver** (the Document-AI auto-map target); routes per §8 incl. `GET/POST /products/{id}/supplier-codes`, `PUT /products/{id}/pack-spec`.

**Acceptance:** resolver unit-tested (exact match, unknown code, inactive product); PO create accepts lines; legacy single-description POs keep working untouched; inline RLS on all 6 tables.

**Note:** real SKU seed data is the long pole (spec §10.5) — schema ships now, client's SKU list loads whenever it arrives; `p1a_11` tightening excludes product FKs until then.

---

## Session 5 — Pillar 5 + RLS sweep + tighten (`p1a_9` → `p1a_11`)

**Branch:** `p1a-9-11-masters-rls-tighten` · **Spec:** §6, §1

**Scope:**
- `p1a_9_warehouses_incoterms`: `warehouses` (seed Mistley Quay + planned secondary), `incoterms` (seed FOB/DAP/DDP/EXW), nullable `warehouse_id` on `DeliveryPoint`, and on `Container`: `sale_type` (`ex_bond`/`delivered`), `incoterm_code`, `title_transfer_point`. Do NOT overload `delivery_type` (§6.2).
- `p1a_10_enable_rls_new_tables`: sweep — verify EVERY table added in Sessions 1–5 has RLS; enable any missed.
- `p1a_11_backfill_not_null`: tighten to `NOT NULL` **only** fully-backfilled FKs (`legal_entity_id` everywhere, `supplier_party_id`); product-related FKs stay nullable until real seed data lands.

**Acceptance:** a query against Supabase anon key returns zero rows from every new table; tighten migration is a separate revision so it can ship later if backfill lags.

---

## Session 6 — Trading P1.6: CustomerInvoiceBatch

**Branch:** `trading-p1.6-customer-invoice-batch` · **Spec:** ROADMAP § Trading P1.6

**Scope:**
- `CustomerInvoiceBatch(id, invoice_number unique, issued_at, total_gbp, customer_id)` + `CustomerInvoiceBatchContainer` junction (multiple containers per outbound invoice, matching `INV-2603-61` covering four containers).
- Numbering: `INV-YYMM-seq` — service-generated, DB-unique constraint, gap-tolerant (sequence per month; on conflict retry). No global lock.
- `CustomerPayment.customer_invoice_ref: str` → nullable FK `customer_invoice_batch_id`; keep the string column as legacy until data migrated, then drop in a follow-up.
- Admin routes: create batch (assign containers, computed `total_gbp` from `sale_price_total`), list, get; AuditLog on create.
- Out of scope (Trading P2, per roadmap): PDF generation, outbound delivery, GDPR retention.

**Acceptance:** one batch ↔ N containers round-trips; duplicate `invoice_number` rejected at DB level; numbering resets per month; idempotency key required on the money-adjacent POST.

---

## Session 7 — P3 scale prep

**Branch:** `p3-scale-prep` · **Spec:** ROADMAP § P3 (#20, #21, #24, #25)

**Scope (4 sub-tasks, commit each separately):**
1. **#20 Read caching:** Redis, 30s TTL on shipment/booking-detail; invalidate on any lifecycle transition (hook `ContainerLifecycleService.recompute()` + booking state changes).
2. **#21 Soft delete + archival:** `deleted_at` pattern on user-facing entities; retention = customs 6 yr / others 2 yr (**checkpoint: confirm client sign-off before merging this sub-task**); queries filter `deleted_at IS NULL` centrally, not per-call-site.
3. **#24 TZ audit:** every `DateTime` column and `utcnow()` call site → timezone-aware; fold in the `python-jose` → `pyjwt` swap here if warnings originate there (ROADMAP §G note).
4. **#25 Load test:** locust scenario — 100 concurrent users on shipment-list + shipment-detail, target p95 < 300ms; document results + any index fixes in `docs/`.

**Acceptance:** ROADMAP "P3 done when" checklist; cache hit ratio visible in logs/metrics; locust run committed with results.

---

## Session 8 (optional, 1 hr) — G1: passlib → bcrypt

**Branch:** `g1-passlib-removal` · **Spec:** ROADMAP § Phase G

Direct `bcrypt.hashpw/checkpw` in `app/core/security.py`, cost from `BCRYPT_ROUNDS`; drop passlib, promote bcrypt to direct dep; prove an old-format hash still verifies. Small, unblocked, removes the Python 3.13 boot failure. Slot it whenever a session finishes early.

---

## Sequencing & rules of thumb

```
S0 (land 1b) → S1 (1c) → S2 (entities) → S3 (parties) → S4 (products) → S5 (masters+RLS+tighten)
                                                                              ↓
                                              S6 (P1.6) → S7 (P3) → [S8 G1 anywhere]
```

- **Strict order S0–S5** (each pillar references the previous — spec §1). S6–S8 are independent of each other.
- **One session, one PR, merged before the next starts.** No stacked branches beyond what exists today.
- If a session balloons: ship what's green, cut a follow-up branch. Never merge with a failing gate.
- After every merge: Claude Code updates CLAUDE.md status + ROADMAP so the next session's context is current.
- Estimated total: 6 required sessions + 2 optional, each ending in a reviewable PR.
