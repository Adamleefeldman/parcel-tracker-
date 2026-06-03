/**
 * Hand-typed mirror of the backend `MoneyRiskOut` schema
 * (`parcel-track/app/schemas/money_risk.py`), powering the mobile "Alerts" /
 * Money-risk tab.
 *
 * **Money fields are `string`.** The route uses `response_model=MoneyRiskOut`,
 * so Pydantic serialises every `Decimal` to a JSON **string** (`"42180.00"`).
 * Keep them as strings end-to-end and format/sum via the `src/lib/money.ts`
 * helpers — never `parseFloat` (see AGENTS.md → Money).
 *
 * Two honest approximations are baked into the backend and surface here, so the
 * UI must not fabricate precision the data doesn't have:
 *  - `total_outstanding` is the **full** sale value of unbanked containers, not
 *    netted against any already-banked tranche (full-exposure view).
 *  - Demurrage countdowns are **whole days** (`Vessel.ata` is a date with no
 *    time component); `days_remaining` is an int and goes negative once free
 *    time has expired. Do NOT render fabricated hours.
 */

import type { ContainerLifecycleStatus } from './enums';

// ── A/R aging ────────────────────────────────────────────────────────────────

/** One aging band. `amount` sums `sale_price_total` of the band's containers. */
export interface ARAgingBucket {
  /** "0-14" | "15-30" | "31-60" | "60+" */
  label: string;
  count: number;
  amount: string;
}

/** A single delivered-but-unbanked container. `days_aged` is approximate
 * (measured from `Container.updated_at` — no precise `delivered_at` yet). */
export interface AgedContainer {
  container_id: string;
  container_number: string;
  booking_id: string;
  lifecycle_status: ContainerLifecycleStatus;
  sale_price_total: string | null;
  days_aged: number;
}

export interface ARAgingSummary {
  total_outstanding: string;
  container_count: number;
  buckets: ARAgingBucket[];
  /** Capped inline drill-in list. */
  containers: AgedContainer[];
  containers_truncated: boolean;
}

// ── Demurrage countdown ───────────────────────────────────────────────────────

export interface DemurrageCountdown {
  booking_id: string;
  container_id: string;
  container_number: string;
  /** A `UKPort` enum value, or null when the BL has no port set. */
  port_of_discharge: string | null;
  /** ISO date (no time component). */
  ata: string;
  free_days: number;
  /** Whole days; negative once free time has expired. */
  days_remaining: number;
  expired: boolean;
  rate_gbp_after: string | null;
}

export interface DemurrageSummary {
  /** Rows with `days_remaining <= DEMURRAGE_WARNING_LEAD_DAYS` (incl. expired). */
  expiring_count: number;
  soonest_days_remaining: number | null;
  /** Soonest-expiring first. */
  items: DemurrageCountdown[];
}

// ── Disputes ──────────────────────────────────────────────────────────────────

/** A disputed container, for the dashboard drill-in. `booking_id` deep-links to
 * the booking where the dispute is acknowledged (the container detail screen). */
export interface DisputedContainer {
  container_id: string;
  container_number: string;
  booking_id: string;
  acknowledged: boolean;
}

export interface DisputeSummary {
  unacknowledged_count: number;
  acknowledged_count: number;
  /** Disputed containers (acknowledged + unacknowledged), oldest first. */
  items: DisputedContainer[];
}

// ── Combined ──────────────────────────────────────────────────────────────────

export interface MoneyRiskOut {
  ar_aging: ARAgingSummary;
  demurrage: DemurrageSummary;
  disputes: DisputeSummary;
}
