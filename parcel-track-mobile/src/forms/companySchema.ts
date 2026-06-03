/**
 * Validation schema for the create-end-customer (company) form
 * (react-hook-form + zod — see AGENTS.md → Forms).
 *
 * Mirrors the backend's single-field rules (`CompanyCreate`): `legal_name`
 * required (non-empty); everything else optional. The one non-trivial mapping is
 * `aliases`: the backend takes a `string[]`, but the form collects a single
 * comma-separated text field — `toCreateBody` splits on comma, trims, and drops
 * blanks (so "Acme, , Acme UK," → ["Acme", "Acme UK"]). An empty aliases field
 * is omitted entirely (not sent as `[]`).
 */

import { z } from 'zod';

import type { CompanyCreate } from '../api/types/admin';

export const companySchema = z.object({
  legal_name: z.string().trim().min(1, 'Legal name is required').max(300, 'Too long (max 300)'),
  /** Comma-separated; split into a string[] in the mapper. */
  aliases: z.string().max(500, 'Too long (max 500)'),
  registration_no: z.string().max(100, 'Too long (max 100)'),
  vat_no: z.string().max(100, 'Too long (max 100)'),
  default_address: z.string().max(500, 'Too long (max 500)'),
});

/** All-string form values (RHF state). Mapped to the body via `toCreateBody`. */
export type CompanyFormValues = z.infer<typeof companySchema>;

export const defaultCompanyFormValues: CompanyFormValues = {
  legal_name: '',
  aliases: '',
  registration_no: '',
  vat_no: '',
  default_address: '',
};

/** Split a comma-separated aliases string into a trimmed, blank-free array. */
export function parseAliases(raw: string): string[] {
  return raw
    .split(',')
    .map((a) => a.trim())
    .filter((a) => a !== '');
}

/**
 * Map validated values to the request body. Trims all fields, omits blank
 * optionals, and parses `aliases` into a `string[]` (omitted when empty).
 */
export function toCreateBody(values: CompanyFormValues): CompanyCreate {
  const t = (s: string) => s.trim();
  const opt = (s: string): string | undefined => (t(s) === '' ? undefined : t(s));
  const aliases = parseAliases(values.aliases);

  return {
    legal_name: t(values.legal_name),
    ...(aliases.length === 0 ? {} : { aliases }),
    ...(opt(values.registration_no) === undefined
      ? {}
      : { registration_no: t(values.registration_no) }),
    ...(opt(values.vat_no) === undefined ? {} : { vat_no: t(values.vat_no) }),
    ...(opt(values.default_address) === undefined
      ? {}
      : { default_address: t(values.default_address) }),
  };
}
