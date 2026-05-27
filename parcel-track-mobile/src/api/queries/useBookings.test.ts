/**
 * Tests for the bookings query helpers.
 *
 * The hook itself (`useBookings`) needs a React renderer to exercise; that
 * setup isn't worth standing up for a one-line wrapper. The thing worth
 * pinning down is the query-key shape — every other hook in this codebase
 * will copy this pattern, so accidental drift is expensive.
 */

import { bookingsQueryKey } from './useBookings';

describe('bookingsQueryKey', () => {
  it('returns ["bookings", filters] with an empty filters object by default', () => {
    expect(bookingsQueryKey()).toEqual(['bookings', {}]);
  });

  it('includes filters in the key so different filters do not share a cache slot', () => {
    const a = bookingsQueryKey({ status: 'paid' });
    const b = bookingsQueryKey({ status: 'pending' });

    expect(a).toEqual(['bookings', { status: 'paid' }]);
    expect(b).toEqual(['bookings', { status: 'pending' }]);
    expect(a).not.toEqual(b);
  });

  it('keeps "bookings" as the first element so cache invalidation by resource works', () => {
    const key = bookingsQueryKey({ status: 'paid', page: 2 });
    expect(key[0]).toBe('bookings');
  });
});
