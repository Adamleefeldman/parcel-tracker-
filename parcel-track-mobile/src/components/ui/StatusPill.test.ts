/**
 * Exhaustiveness + tone-semantics check for the status→tone mappings.
 *
 * The TS `Record<EnumType, PillTone>` type already enforces exhaustiveness at
 * compile time, but a runtime test guards against accidental `as any` casts and
 * documents the prototype-aligned tone contract (Phase 9: in-flight shipping
 * states are blue/`info`, not amber).
 */

import type { BookingStatus, ContainerLifecycleStatus } from '../../api/types/enums';
import { BOOKING_TONES, LIFECYCLE_TONES, humanizeStatus } from './statusPillMapping';

const ALL_BOOKING_STATUSES: BookingStatus[] = [
  'draft',
  'po_submitted',
  'invoice_received',
  'payment_confirmed',
  'bl_issued',
  'in_transit',
  'cleared',
  'complete',
];

const ALL_LIFECYCLE_STATUSES: ContainerLifecycleStatus[] = [
  'ordered',
  'at_sea',
  'arrived',
  'import_cleared',
  'delivered',
  'invoiced',
  'paid',
  'banked',
  'closed',
  'disputed',
];

describe('StatusPill mappings', () => {
  it.each(ALL_BOOKING_STATUSES)('maps booking status %s to a defined tone', (s) => {
    expect(BOOKING_TONES[s]).toBeDefined();
  });

  it.each(ALL_LIFECYCLE_STATUSES)('maps lifecycle status %s to a defined tone', (s) => {
    expect(LIFECYCLE_TONES[s]).toBeDefined();
  });

  it('routes disputed lifecycle to error tone (problem state)', () => {
    expect(LIFECYCLE_TONES.disputed).toBe('error');
  });

  it('routes draft/po_submitted booking and ordered container to default tone (idle/early)', () => {
    expect(BOOKING_TONES.draft).toBe('default');
    expect(BOOKING_TONES.po_submitted).toBe('default');
    expect(LIFECYCLE_TONES.ordered).toBe('default');
  });

  it('routes in-flight shipping statuses to info (blue) tone', () => {
    expect(BOOKING_TONES.bl_issued).toBe('info');
    expect(BOOKING_TONES.in_transit).toBe('info');
    expect(BOOKING_TONES.cleared).toBe('info');
    expect(LIFECYCLE_TONES.at_sea).toBe('info');
    expect(LIFECYCLE_TONES.arrived).toBe('info');
    expect(LIFECYCLE_TONES.import_cleared).toBe('info');
    expect(LIFECYCLE_TONES.delivered).toBe('info');
  });

  it('routes money-in-progress statuses to warning (amber) tone', () => {
    expect(BOOKING_TONES.invoice_received).toBe('warning');
    expect(BOOKING_TONES.payment_confirmed).toBe('warning');
    expect(LIFECYCLE_TONES.invoiced).toBe('warning');
  });

  it('routes terminal-good statuses to success tone', () => {
    expect(BOOKING_TONES.complete).toBe('success');
    expect(LIFECYCLE_TONES.paid).toBe('success');
    expect(LIFECYCLE_TONES.banked).toBe('success');
    expect(LIFECYCLE_TONES.closed).toBe('success');
  });
});

describe('humanizeStatus', () => {
  it('uppercases the first letter and replaces underscores with spaces', () => {
    expect(humanizeStatus('in_transit')).toBe('In transit');
    expect(humanizeStatus('payment_confirmed')).toBe('Payment confirmed');
    expect(humanizeStatus('draft')).toBe('Draft');
  });

  it('handles single-word input', () => {
    expect(humanizeStatus('complete')).toBe('Complete');
  });

  it('returns empty string unchanged', () => {
    expect(humanizeStatus('')).toBe('');
  });
});
