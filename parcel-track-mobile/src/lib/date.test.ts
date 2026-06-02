/**
 * Pin the timezone to a negative UTC offset BEFORE importing the module under
 * test. `America/Los_Angeles` (UTC-7/-8) is where the date-only TZ-rollback bug
 * manifests: `new Date("2026-06-01")` is midnight UTC, which is the previous
 * evening local, so a naive formatter renders "May 31". This guards the fix.
 */
process.env.TZ = 'America/Los_Angeles';

import { formatDate, formatDateTime } from './date';

describe('formatDate', () => {
  it('formats a date-only string', () => {
    expect(formatDate('2026-06-01')).toBe('Jun 1, 2026');
  });

  it('does NOT shift a date-only value back a day in a negative-offset TZ', () => {
    // The whole point of the noon-parse: 1 June stays 1 June, never 31 May.
    const out = formatDate('2026-06-01');
    expect(out).toContain('Jun');
    expect(out).toContain('1');
    expect(out).not.toContain('May');
  });

  it('handles a year-boundary date-only value without rolling into last year', () => {
    const out = formatDate('2026-01-01');
    expect(out).toContain('Jan');
    expect(out).toContain('2026');
    expect(out).not.toContain('Dec');
    expect(out).not.toContain('2025');
  });

  it('renders null/undefined/empty as an em dash', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate(undefined)).toBe('—');
    expect(formatDate('')).toBe('—');
  });

  it('echoes an unparseable string back unchanged', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date');
  });

  it('formats a full ISO timestamp down to its date', () => {
    // A timestamp with an explicit Z carries its own offset; we still render a
    // sensible day (here, late evening UTC is same-day in LA).
    expect(formatDate('2026-06-01T18:00:00Z')).toBe('Jun 1, 2026');
  });
});

describe('formatDateTime', () => {
  it('includes a time component', () => {
    const out = formatDateTime('2026-06-01T18:30:00Z');
    // 18:30 UTC → 11:30 in LA (PDT). Assert it carries the date + a clock.
    expect(out).toContain('Jun 1, 2026');
    expect(out).toMatch(/\d{1,2}:\d{2}/);
  });

  it('renders null/undefined/empty as an em dash', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime(undefined)).toBe('—');
    expect(formatDateTime('')).toBe('—');
  });

  it('echoes an unparseable string back unchanged', () => {
    expect(formatDateTime('nope')).toBe('nope');
  });
});
