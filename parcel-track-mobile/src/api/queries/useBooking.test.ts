/**
 * Tests for the single-booking query helpers. As with useBookings, the hook
 * body itself needs a React renderer to exercise meaningfully; what matters
 * for cache correctness is the query-key shape.
 */

import { bookingQueryKey } from './useBooking';

describe('bookingQueryKey', () => {
  it('returns ["booking", id]', () => {
    expect(bookingQueryKey('abc')).toEqual(['booking', 'abc']);
  });

  it('keeps "booking" (singular) as the first element to avoid collision with the bookings list key', () => {
    const key = bookingQueryKey('xyz');
    expect(key[0]).toBe('booking');
  });

  it('produces stable, deep-equal keys for the same id', () => {
    expect(bookingQueryKey('id-1')).toEqual(bookingQueryKey('id-1'));
  });
});
