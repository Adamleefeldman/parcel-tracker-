/**
 * Pure booking-progress model — the status→step mapping extracted from
 * `BookingStepper` so the stepper (booking detail) and the segmented progress
 * bar on `BookingCard` (bookings list) derive position from ONE source. The
 * eight booking stages are a fixed forward sequence, so position is just the
 * status's index.
 *
 * `disputed` is a container side-state, not a `BookingStatus`, so it never
 * appears here.
 */

import type { BookingStatus } from '../../api/types/enums';

/** The booking lifecycle stages, in order. */
export const BOOKING_STAGES: readonly BookingStatus[] = [
  'draft',
  'po_submitted',
  'invoice_received',
  'payment_confirmed',
  'bl_issued',
  'in_transit',
  'cleared',
  'complete',
];

/**
 * 0-based stage index for a status. Defensive: an unknown value (a backend
 * enum the app predates) clamps to 0 rather than rendering a -1 hole.
 */
export function bookingStageIndex(status: BookingStatus): number {
  return Math.max(0, BOOKING_STAGES.indexOf(status));
}
