import { formatRelativeTime } from './relativeTime';

const now = new Date('2026-05-31T12:00:00Z');

describe('formatRelativeTime', () => {
  it('shows "just now" under a minute', () => {
    expect(formatRelativeTime('2026-05-31T11:59:30Z', now)).toBe('just now');
  });

  it('shows minutes', () => {
    expect(formatRelativeTime('2026-05-31T11:30:00Z', now)).toBe('30m ago');
  });

  it('shows hours', () => {
    expect(formatRelativeTime('2026-05-31T09:00:00Z', now)).toBe('3h ago');
  });

  it('shows days under a week', () => {
    expect(formatRelativeTime('2026-05-29T12:00:00Z', now)).toBe('2d ago');
  });

  it('falls back to an absolute date past a week', () => {
    expect(typeof formatRelativeTime('2026-01-01T12:00:00Z', now)).toBe('string');
    expect(formatRelativeTime('2026-01-01T12:00:00Z', now)).not.toMatch(/ago/);
  });

  it('echoes back an unparseable input', () => {
    expect(formatRelativeTime('not-a-date', now)).toBe('not-a-date');
  });
});
