/**
 * Shared date formatting for screens.
 *
 * Two formatters, one TZ-safety rule. The backend sends two shapes of date:
 *
 *   - **Date-only** (`"2026-06-01"`) for calendar fields like a PO date or a
 *     BL date. Parsing `new Date("2026-06-01")` treats it as **midnight UTC**,
 *     which in any negative-offset timezone (the Americas) rolls back to the
 *     *previous* day when rendered locally — so a 1 June PO shows as 31 May.
 *     We parse date-only values at **local noon** (`"2026-06-01T12:00:00"`) so
 *     the displayed day is stable regardless of the device timezone.
 *   - **Full timestamp** (`"2026-06-01T09:30:00Z"`) for event times like
 *     `delivered_at`. These carry their own offset, so we parse them as-is and
 *     let `toLocaleString` localize the wall-clock time.
 *
 * Both echo an unparseable input back unchanged and render null/empty as "—".
 * This replaces four inline copies (booking detail, container detail, bookings
 * list, DocumentsList) that were inconsistent — only the container screen had
 * the noon-parse, so the same date-only string could render as a different day
 * on different screens.
 */

const EMPTY = '—';

/** True for a bare `YYYY-MM-DD` (no time component). */
function isDateOnly(iso: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso);
}

/** Parse a wire date, noon-anchoring date-only strings to dodge TZ rollback. */
function parse(iso: string): Date {
  return new Date(isDateOnly(iso) ? `${iso}T12:00:00` : iso);
}

/**
 * Format a date as `"1 Jun 2026"`. Date-only strings are noon-anchored so the
 * day never shifts across timezones. Null/undefined/empty → `"—"`; an
 * unparseable string is echoed back unchanged.
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const d = parse(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

/**
 * Format a timestamp as `"1 Jun 2026, 09:30"`. Use for event times that carry
 * a clock component (`delivered_at`, cutoffs). Null/undefined/empty → `"—"`;
 * an unparseable string is echoed back unchanged.
 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const d = parse(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
