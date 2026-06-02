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
export function formatMoney(amount: string | number | null | undefined, currency = 'GBP'): string {
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
 * Sum a list of decimal-string money values exactly, returning a decimal
 * string with two fractional digits (e.g. `["0.10", "0.20"]` → `"0.30"`,
 * never `0.30000000000000004`). Null/undefined/empty entries are skipped, so
 * masked or absent amounts don't break the total. An empty (or all-null) list
 * sums to `"0.00"`.
 *
 * The maths is done in integer **cents** — the values are split lexically into
 * integer + fractional parts (no `parseFloat`), so no float rounding ever
 * touches a money value. This is the canonical way to total money client-side
 * (see AGENTS.md → Money); never `reduce` with `parseFloat`. Values up to ~90
 * trillion sum safely (well within `Number.MAX_SAFE_INTEGER` cents); anything
 * not matching a plain decimal shape is skipped defensively.
 */
export function sumDecimalStrings(values: (string | null | undefined)[]): string {
  let cents = 0;
  for (const value of values) {
    if (value === null || value === undefined || value === '') continue;
    const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim());
    if (!match) continue; // not a clean decimal — skip defensively
    const [, sign, intPart, fracRaw = ''] = match;
    const valueCents = Number(intPart) * 100 + Number((fracRaw + '00').slice(0, 2));
    cents += sign === '-' ? -valueCents : valueCents;
  }
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  const intPart = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, '0');
  return `${sign}${intPart}.${frac}`;
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
