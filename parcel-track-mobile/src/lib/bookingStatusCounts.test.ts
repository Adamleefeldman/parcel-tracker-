import { BOOKING_STATUSES, countByStatus, totalCount } from './bookingStatusCounts';
import type { Booking } from '../api/queries/useBookings';

function booking(status: string): Booking {
  return {
    id: `${status}-${Math.random()}`,
    reference: 'R',
    booking_number: null,
    status,
    created_at: '',
    updated_at: '',
  };
}

describe('countByStatus', () => {
  it('groups bookings by status', () => {
    const counts = countByStatus([booking('draft'), booking('draft'), booking('in_transit')]);
    expect(counts.draft).toBe(2);
    expect(counts.in_transit).toBe(1);
    expect(counts.complete).toBe(0);
  });

  it('returns every status key (all zero) for empty input', () => {
    const counts = countByStatus([]);
    expect(Object.keys(counts).sort()).toEqual([...BOOKING_STATUSES].sort());
    BOOKING_STATUSES.forEach((s) => expect(counts[s]).toBe(0));
  });

  it('ignores statuses outside the known enum', () => {
    const counts = countByStatus([booking('not_a_real_status')]);
    expect(totalCount(counts)).toBe(0);
  });
});

describe('totalCount', () => {
  it('sums all status counts', () => {
    expect(totalCount(countByStatus([booking('draft'), booking('cleared'), booking('complete')]))).toBe(
      3,
    );
  });
});
