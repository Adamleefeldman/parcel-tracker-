---
name: seed-demo-data
description: Seed the local Postgres with demo trading data (bookings, POs, containers, payments) for manual/device verification. Use whenever a manual check, Expo Go test, or screenshot needs data in the local DB — and ALWAYS instead of hand-writing INSERT statements, which have repeatedly failed on Postgres enum labels, uuid casts, and junction-table defaults.
---

# Seed demo data

The canonical way to put realistic data into the **local** database is the
maintained script — it uses the app's own SQLAlchemy models, so enum labels,
uuids, and defaults are always correct:

```bash
cd /Users/adamfeldman/parcel-tracker/parcel-track
uv run python scripts/seed_demo.py                  # seed all scenarios
uv run python scripts/seed_demo.py --scenario basic # one scenario
uv run python scripts/seed_demo.py --reset          # remove DEMO- rows first
```

Scenarios: `basic` (early-state booking + PO + invoice + containers),
`in-transit` (BL + vessel departed), `delivered-unbanked` (feeds the
money-risk / A/R-aging screens), `disputed` (unacknowledged dispute), `all`.

## Rules

1. **Never write ad-hoc INSERT/UPDATE SQL to seed data.** Past sessions burned
   six consecutive attempts on `invalid input value for enum postatus:
   "submitted"`, `null value in column "id"` on junction tables, and uuid/text
   cast errors. The enum trap is nasty: most Postgres enums store the
   **uppercase Python member name** (`SUBMITTED`), but a few
   (`containerlifecyclestatus`, `ukport`, `customerpaymentmethod`,
   `deliverytype`) store **lowercase values** via `lowercase_enum()` — you
   cannot guess which from the Python code alone. The ORM handles both. If the
   script lacks a state you need, **extend the script** (it's idempotent and
   keyed on `DEMO-` refs) — don't bypass it.
2. **Check which DB you're hitting.** The host `.env` and the API container
   both target local Docker Postgres (`parceltrack-postgres`). The script
   refuses non-local hosts unless `--allow-remote` — never use that flag
   against prod without the user explicitly asking.
3. **Precise lifecycle states**: booking `status` and container
   `lifecycle_status` are normally *derived* by services. The script sets them
   consistently with the state machines; if you set states another way, keep
   them consistent with `booking_service.py` / `container_lifecycle_service.py`
   or the app will behave confusingly during the demo.
4. **Verify the API sees it**: `curl -fsS http://localhost:8000/health`, then
   check via the API (or `docker exec parceltrack-postgres psql ...` for a
   quick count). If the data "isn't showing up", you probably seeded a
   different DB than the API reads — see the two-database gotcha in
   `parcel-track/CLAUDE.md`.
5. Login for demo checks: reuse the existing admin; the script prints the
   email it used at the end of its run.
