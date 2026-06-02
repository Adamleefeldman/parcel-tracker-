/**
 * Pure-logic half of `StatusPill`. Split out from `StatusPill.tsx` so the
 * mappings + label helper are testable under the ts-jest node config (which
 * doesn't transform JSX). See `jest.config.js`.
 *
 * Tone rules (Phase 9, prototype-aligned — the prototype colors in-flight
 * SHIPPING states blue, not amber):
 *   - info (blue)    in-flight position: bl_issued, in_transit, cleared,
 *                    at_sea, arrived, import_cleared, delivered
 *   - warning (amber) money in progress: invoice_received, payment_confirmed,
 *                    invoiced (A/R outstanding)
 *   - success (green) terminal-good: complete, paid, banked, closed
 *   - error (red)    problem: disputed
 *   - default (grey) early/idle: draft, po_submitted, ordered
 *
 * Judgment calls (prototype didn't show every enum explicitly — noted in the
 * Phase 9 PR): `po_submitted`/`payment_confirmed` (mid-flow), `delivered`
 * (kept in the blue "physical movement" family, before the amber money phase),
 * and `invoiced` (amber = A/R outstanding).
 *
 * `Record<BookingStatus, PillTone>` is exhaustive — adding a new enum value to
 * `src/api/types/enums.ts` will fail TS until the mapping is updated.
 */

import type { BookingStatus, ContainerLifecycleStatus } from '../../api/types/enums';
import type { PillTone } from './Pill';

export const BOOKING_TONES: Record<BookingStatus, PillTone> = {
  draft: 'default',
  po_submitted: 'default',
  invoice_received: 'warning',
  payment_confirmed: 'warning',
  bl_issued: 'info',
  in_transit: 'info',
  cleared: 'info',
  complete: 'success',
};

export const LIFECYCLE_TONES: Record<ContainerLifecycleStatus, PillTone> = {
  ordered: 'default',
  at_sea: 'info',
  arrived: 'info',
  import_cleared: 'info',
  delivered: 'info',
  invoiced: 'warning',
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
