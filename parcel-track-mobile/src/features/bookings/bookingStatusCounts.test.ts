import { countByStatus, formatStatusCounts } from './bookingStatusCounts';

describe('countByStatus', () => {
  it('counts bookings per status', () => {
    const counts = countByStatus([
      { status: 'in_transit' },
      { status: 'in_transit' },
      { status: 'complete' },
    ]);
    expect(counts).toEqual({ in_transit: 2, complete: 1 });
  });

  it('returns an empty record for an empty list', () => {
    expect(countByStatus([])).toEqual({});
  });

  it('keeps unknown statuses rather than dropping them', () => {
    expect(countByStatus([{ status: 'future_status' }])).toEqual({ future_status: 1 });
  });
});

describe('formatStatusCounts', () => {
  it('renders non-zero counts in lifecycle order', () => {
    const text = formatStatusCounts({ complete: 2, draft: 1, in_transit: 3 });
    expect(text).toBe('1 draft · 3 in transit · 2 complete');
  });

  it('omits zero counts', () => {
    expect(formatStatusCounts({ draft: 0, cleared: 1 })).toBe('1 cleared');
  });

  it('returns an empty string for no counts (caller hides the strip)', () => {
    expect(formatStatusCounts({})).toBe('');
  });

  it('appends unknown statuses after the known stages', () => {
    const text = formatStatusCounts({ future_status: 1, draft: 2 });
    expect(text).toBe('2 draft · 1 future status');
  });
});
