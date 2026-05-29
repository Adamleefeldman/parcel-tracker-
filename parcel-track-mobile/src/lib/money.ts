/**
 * Decimal-safe money helpers.
 *
 * The backend speaks `Decimal` over the wire. For the payment create + list
 * shapes (Pydantic models) those serialize as JSON strings (`"1000.50"`);
 * we keep them as `string` end-to-end and NEVER parse to float for storage or
 * submission — float rounding would corrupt money. The aggregate endpoint is
 * the one exception: it returns a plain dict (no response_model), so FastAPI's
 * jsonable_encoder serializes its Decimals as JSON **numbers**. Hence the
 * helpers here accept `string | number`.
 *
 * The ONLY place a money value may be coerced to a float is `parseRatio`, and
 * only because a progress-bar width is inherently cosmetic — its result never
 * round-trips back to the server.
 */

/** Unsigned decimal, up to 2 fractional digits. Used for amounts/expenses. */
export const DECIMAL_RE = /^\d+(\.\d{1,2})?$/;
/** Signed decimal (variance may be negative = short, positive = over). */
export const SIGNED_DECIMAL_RE = /^-?\d+(\.\d{1,2})?$/;

/** Shown in place of a null/masked money value (non-admins see this). */
export const EMPTY_MONEY = '—';

const CURRENCY_SYMBOLS: Record<string, string> = {
  GBP: '£',
  USD: '$',
  EUR: '€',
};

/**
 * Format a money value for display: `"£1,000.50"`. Null/undefined/empty →
 * `"—"` (the masked / not-set case). Works on the wire's strings *and* the
 * aggregate's numbers without ever doing float maths on the value — it splits
 * the decimal lexically and groups the integer part, so exact digits survive.
 */
export function formatMoney(
  amount: string | number | null | undefined,
  currency = 'GBP',
): string {
  if (amount === null || amount === undefined || amount === '') return EMPTY_MONEY;
  const raw = typeof amount === 'number' ? String(amount) : amount.trim();
  const symbol = CURRENCY_SYMBOLS[currency] ?? `${currency} `;

  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(raw);
  if (!match) {
    // Not a clean decimal (shouldn't come from the API) — show it prefixed.
    return `${symbol}${raw}`;
  }
  const [, sign, intPart, fracRaw = ''] = match;
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const frac = (fracRaw + '00').slice(0, 2);
  return `${sign}${symbol}${grouped}.${frac}`;
}

/**
 * Cosmetic ratio for the banked-progress bar. Returns a clamped 0..1 fraction,
 * or null when the denominator is missing/zero (caller hides the bar). This is
 * the one sanctioned float coercion of a money value — the output drives a bar
 * width only and never returns to the server.
 */
export function parseRatio(
  part: string | number | null | undefined,
  whole: string | number | null | undefined,
): number | null {
  if (part == null || whole == null) return null;
  const p = typeof part === 'number' ? part : parseFloat(part);
  const w = typeof whole === 'number' ? whole : parseFloat(whole);
  if (!Number.isFinite(p) || !Number.isFinite(w) || w <= 0) return null;
  return Math.max(0, Math.min(1, p / w));
}
