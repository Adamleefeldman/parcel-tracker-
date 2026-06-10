/**
 * Pure formatting helpers for the Admin audit-log viewer.
 *
 * `humanizeAction` turns a dotted/underscored backend action code into a
 * readable sentence; `prettyJson` defensively pretty-prints the stored
 * `old_value`/`new_value` snapshots (which may be null or non-JSON).
 */

/**
 * `booking.status_changed` → `Booking status changed`. Splits on `.`/`_`,
 * capitalises only the first word (the rest stay lower-case for a sentence
 * feel), and echoes the input back unchanged when it's empty.
 */
export function humanizeAction(raw: string): string {
  if (!raw) return raw;
  const words = raw.split(/[._]/).filter(Boolean);
  if (words.length === 0) return raw;
  const [first, ...rest] = words;
  return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(' ');
}

/**
 * Pretty-print a stored audit value. The backend writes `old_value`/`new_value`
 * as `json.dumps(...)` strings, but some rows are null and we must never assume
 * the string parses. Returns re-indented JSON when it parses, the raw string
 * when it doesn't, and `null` for absent/blank values (so the caller can hide
 * the row entirely).
 */
export function prettyJson(raw: string | null | undefined): string | null {
  if (raw == null) return null;
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return raw;
  }
}
