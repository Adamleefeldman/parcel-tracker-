/**
 * Validation schema for the edit-port-template form (react-hook-form + zod).
 *
 * Port templates are **edit/upsert-only** — the six UK ports are a fixed enum,
 * so there's no "create a port"; the form pre-fills from the existing template
 * (or defaults) and PUTs to upsert. Mirrors the backend `PortTemplateUpsert`
 * single-field rules: free-days are required non-negative **ints**; rates are
 * optional non-negative **decimals**.
 *
 * Money discipline: the rate fields stay **strings** end-to-end (backend
 * `Decimal` → JSON string) — `toUpsertBody` never `parseFloat`s them. Only the
 * free-day counts convert to `number`.
 */

import { z } from 'zod';

import { DECIMAL_RE } from '../lib/money';
import type { PortTemplateUpsert } from '../api/types/admin';

/** A non-negative whole number as a string (free-day counts). */
const FREE_DAYS_RE = /^\d+$/;

/** Optional unsigned decimal rate: a valid amount, or blank (= not set). */
const optionalRate = z
  .string()
  .regex(DECIMAL_RE, 'Enter a valid rate (up to 2 decimals)')
  .or(z.literal(''));

export const portTemplateSchema = z.object({
  free_days_detention: z.string().regex(FREE_DAYS_RE, 'Whole number of days (0 or more)'),
  free_days_demurrage: z.string().regex(FREE_DAYS_RE, 'Whole number of days (0 or more)'),
  detention_rate_gbp_after: optionalRate,
  demurrage_rate_gbp_after: optionalRate,
});

/** All-string form values (RHF state). Mapped to the body via `toUpsertBody`. */
export type PortTemplateFormValues = z.infer<typeof portTemplateSchema>;

export const defaultPortTemplateFormValues: PortTemplateFormValues = {
  free_days_detention: '0',
  free_days_demurrage: '0',
  detention_rate_gbp_after: '',
  demurrage_rate_gbp_after: '',
};

/**
 * Map validated values to the PUT body. Free-days → integer `number`; rate
 * fields stay decimal **strings** (omitted when blank — "rate not set").
 */
export function toUpsertBody(values: PortTemplateFormValues): PortTemplateUpsert {
  const detention = values.detention_rate_gbp_after.trim();
  const demurrage = values.demurrage_rate_gbp_after.trim();
  return {
    free_days_detention: Number(values.free_days_detention.trim()),
    free_days_demurrage: Number(values.free_days_demurrage.trim()),
    ...(detention === '' ? {} : { detention_rate_gbp_after: detention }),
    ...(demurrage === '' ? {} : { demurrage_rate_gbp_after: demurrage }),
  };
}
