import type { BookingStatus } from '../../api/types/enums';
import { BOOKING_STAGES, bookingStageIndex } from './bookingProgress';

describe('BOOKING_STAGES', () => {
  it('covers the full 8-stage booking lifecycle in order', () => {
    expect(BOOKING_STAGES).toEqual([
      'draft',
      'po_submitted',
      'invoice_received',
      'payment_confirmed',
      'bl_issued',
      'in_transit',
      'cleared',
      'complete',
    ]);
  });
});

describe('bookingStageIndex', () => {
  it('maps each status to its position', () => {
    BOOKING_STAGES.forEach((status, i) => {
      expect(bookingStageIndex(status)).toBe(i);
    });
  });

  it('starts at draft and ends at complete', () => {
    expect(bookingStageIndex('draft')).toBe(0);
    expect(bookingStageIndex('complete')).toBe(BOOKING_STAGES.length - 1);
  });

  it('clamps an unknown status to 0 instead of -1', () => {
    expect(bookingStageIndex('not_a_status' as BookingStatus)).toBe(0);
  });
});
