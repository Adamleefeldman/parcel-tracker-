/**
 * Pure status-grouping for the dashboard. The bookings list has no faceted
 * count endpoint, so the dashboard fetches a page (limit=200) and groups
 * client-side here. Caps at one page — see the dashboard note for the
 * exact-count upgrade path.
 */

import type { Booking } from '../api/queries/useBookings';
import type { BookingStatus } from '../api/types/enums';

export const BOOKING_STATUSES: BookingStatus[] = [
  'draft',
  'po_submitted',
  'invoice_received',
  'payment_confirmed',
  'bl_issued',
  'in_transit',
  'cleared',
  'complete',
];

export type StatusCounts = Record<BookingStatus, number>;

function emptyCounts(): StatusCounts {
  return Object.fromEntries(BOOKING_STATUSES.map((s) => [s, 0])) as StatusCounts;
}

export function countByStatus(bookings: Booking[]): StatusCounts {
  const counts = emptyCounts();
  for (const booking of bookings) {
    if (booking.status in counts) {
      counts[booking.status as BookingStatus] += 1;
    }
  }
  return counts;
}

export function totalCount(counts: StatusCounts): number {
  return BOOKING_STATUSES.reduce((sum, status) => sum + counts[status], 0);
}
