/**
 * Compact relative-time formatter for alert rows ("3h ago"). Falls back to an
 * absolute date for anything older than a week, and echoes the input back
 * unchanged when it isn't a parseable date. `now` is injectable for testing.
 */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;

  const seconds = Math.round((now.getTime() - d.getTime()) / 1000);
  if (seconds < 60) return 'just now';

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;

  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}
