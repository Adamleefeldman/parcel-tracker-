/**
 * Pure-logic half of `StatusPill`. Split out from `StatusPill.tsx` so the
 * mappings + label helper are testable under the ts-jest node config (which
 * doesn't transform JSX). See `jest.config.js`.
 *
 * Tone rules:
 *   - terminal-good (complete, closed, banked, paid, invoiced) → success
 *   - in-flight    (in_transit, at_sea, arrived, import_cleared, delivered,
 *                   bl_issued, cleared, payment_confirmed, invoice_received,
 *                   po_submitted) → warning
 *   - problem      (disputed) → error
 *   - early/idle   (draft, ordered) → default
 *
 * `Record<BookingStatus, PillTone>` is exhaustive — adding a new enum value
 * to `src/api/types/enums.ts` will fail TS until the mapping is updated.
 */

import type { BookingStatus, ContainerLifecycleStatus } from '../../api/types/enums';
import type { PillTone } from './Pill';

export const BOOKING_TONES: Record<BookingStatus, PillTone> = {
  draft: 'default',
  po_submitted: 'warning',
  invoice_received: 'warning',
  payment_confirmed: 'warning',
  bl_issued: 'warning',
  in_transit: 'warning',
  cleared: 'warning',
  complete: 'success',
};

export const LIFECYCLE_TONES: Record<ContainerLifecycleStatus, PillTone> = {
  ordered: 'default',
  at_sea: 'warning',
  arrived: 'warning',
  import_cleared: 'warning',
  delivered: 'warning',
  invoiced: 'success',
  paid: 'success',
  banked: 'success',
  closed: 'success',
  disputed: 'error',
};

export function humanizeStatus(raw: string): string {
  if (!raw) return raw;
  const words = raw.split('_');
  const first = words[0]!.charAt(0).toUpperCase() + words[0]!.slice(1);
  return [first, ...words.slice(1)].join(' ');
}
