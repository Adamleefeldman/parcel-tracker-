/**
 * Pure presentation helpers for the Money-risk dashboard. Kept framework-free
 * and unit-tested so the screen + hero cards are assembly, not logic.
 *
 * The honest-precision rule lives here: demurrage countdowns are **whole days**
 * (the backend `Vessel.ata` is a date, so `days_remaining` is an int). We never
 * render fabricated hours — the prototype's "2d 14h" is design flavour, not
 * data. See `src/api/types/moneyRisk.ts`.
 */

import { sumDecimalStrings } from '../../lib/money';
import type { ARAgingBucket, DemurrageCountdown } from '../../api/types/moneyRisk';
import type { PillTone } from '../../components/ui';

/** Bucket labels considered "aged" for the Bookings-tab hero card (30+ days). */
const AGED_BUCKET_LABELS = ['31-60', '60+'];

/**
 * Whole-day countdown label. `0` → "Today", positive → "Nd" (e.g. "2d"),
 * negative (expired) → "Expired". No hours — `days_remaining` has none.
 */
export function formatDaysRemaining(days: number): string {
  if (days < 0) return 'Expired';
  if (days === 0) return 'Today';
  return `${days}d`;
}

/**
 * Tone for a demurrage row by urgency: expired/0 → error, within the warning
 * lead → warning, otherwise default. Mirrors the prototype's red/amber dots.
 */
export function demurrageTone(
  item: Pick<DemurrageCountdown, 'days_remaining' | 'expired'>,
): PillTone {
  if (item.expired || item.days_remaining <= 0) return 'error';
  if (item.days_remaining <= DEMURRAGE_WARNING_LEAD_DAYS) return 'warning';
  return 'default';
}

/** Matches the backend `DEMURRAGE_WARNING_LEAD_DAYS`; rows at/under this are
 * counted in `expiring_count`. Used here only to tint near-expiry rows amber. */
export const DEMURRAGE_WARNING_LEAD_DAYS = 3;

/**
 * Tone for an A/R bucket by age band: the oldest band (60+) is the problem
 * (error), 31-60 is attention (warning), the fresh bands are neutral.
 */
export function arBucketTone(label: string): PillTone {
  if (label === '60+') return 'error';
  if (label === '31-60') return 'warning';
  return 'default';
}

/**
 * Aged (30+ days) exposure for the Bookings-tab hero card: the summed amount +
 * container count of the 31-60 and 60+ buckets. Summed exactly via
 * `sumDecimalStrings` (never `parseFloat`). Returns a decimal **string** amount.
 */
export function agedExposure(buckets: ARAgingBucket[]): { amount: string; count: number } {
  const aged = buckets.filter((b) => AGED_BUCKET_LABELS.includes(b.label));
  return {
    amount: sumDecimalStrings(aged.map((b) => b.amount)),
    count: aged.reduce((sum, b) => sum + b.count, 0),
  };
}

/** Tone for the disputes card: any unacknowledged dispute is attention. */
export function disputesTone(unacknowledgedCount: number): PillTone {
  return unacknowledgedCount > 0 ? 'warning' : 'success';
}
