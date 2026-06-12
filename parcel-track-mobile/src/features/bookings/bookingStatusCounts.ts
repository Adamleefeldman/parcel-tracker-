/**
 * Client-side status rollup for the bookings landing strip — "3 in transit ·
 * 1 cleared · 2 complete". Pure: derived from the already-fetched list page,
 * never a second request.
 */

import type { BookingStatus } from '../../api/types/enums';
import { humanizeStatus } from '../../components/ui/statusPillMapping';
import { BOOKING_STAGES } from './bookingProgress';

/** Count bookings per status. Unknown status strings are counted as-is. */
export function countByStatus(items: readonly { status: string }[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    counts[item.status] = (counts[item.status] ?? 0) + 1;
  }
  return counts;
}

/**
 * Render the non-zero counts in lifecycle order: `"2 in transit · 1 complete"`.
 * Statuses outside the known stage list are appended at the end rather than
 * dropped. Empty input → empty string (callers hide the strip).
 */
export function formatStatusCounts(counts: Record<string, number>): string {
  const known = BOOKING_STAGES.filter((s) => counts[s]);
  const unknown = Object.keys(counts).filter(
    (s) => counts[s] && !BOOKING_STAGES.includes(s as BookingStatus),
  );
  return [...known, ...unknown]
    .map((status) => `${counts[status]} ${humanizeStatus(status).toLowerCase()}`)
    .join(' · ');
}
