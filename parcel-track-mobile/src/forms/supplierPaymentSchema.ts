/**
 * Validation schema for the record-supplier-payment form (react-hook-form +
 * zod — the standard for non-trivial forms; see AGENTS.md → Forms).
 *
 * The smaller, simpler sibling of `customerPaymentSchema`. Money discipline is
 * the same: `amount` stays a **string** through the form and into the request
 * body. The schema validates the string's *shape* (decimal regex, positivity
 * via a lexical digit check) without ever parsing to float.
 *
 * Currency is fixed to `"USD"` (no other currency is supported) — it is not a
 * form field; `toCreateBody` hard-codes it. Status is server-set, so it never
 * appears here either.
 *
 * Mirrors only the backend's single-field rule (`SupplierPaymentCreate`):
 * `amount > 0`. There is no cross-field server validation, so none here.
 */

import { z } from 'zod';

import { DECIMAL_RE } from '../lib/money';
import type { SupplierPaymentCreate } from '../api/types/supplierPayment';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export const supplierPaymentSchema = z.object({
  swift_ref: z.string().trim().min(1, 'SWIFT reference is required').max(200, 'Too long (max 200)'),
  payment_date: z.string().regex(DATE_RE, 'Pick a date'),
  amount: z
    .string()
    .regex(DECIMAL_RE, 'Enter a valid amount (up to 2 decimals)')
    .refine((v) => /[1-9]/.test(v), 'Amount must be greater than zero'),
  // Select starts blank; `.includes` (not `v === 'full' || …`) keeps the
  // inferred type a plain string so the '' default validates as "not chosen
  // yet" — a union-equality predicate is read as a type guard in TS 5.5+ and
  // would reject the '' default.
  payment_type: z
    .string()
    .refine((v) => ['full', 'partial', 'deposit'].includes(v), 'Select a payment type'),
  bank_name: z.string().max(200, 'Too long (max 200)'),
  notes: z.string(),
});

/** All-string form values (RHF state). Mapped to the body via `toCreateBody`. */
export type SupplierPaymentFormValues = z.infer<typeof supplierPaymentSchema>;

/** Today as `YYYY-MM-DD` in local time — the default payment date. */
export function todayIso(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

export const defaultSupplierPaymentFormValues: SupplierPaymentFormValues = {
  swift_ref: '',
  payment_date: todayIso(),
  amount: '',
  payment_type: '',
  bank_name: '',
  notes: '',
};

/**
 * Map validated form values to the request body. Blank optional fields are
 * omitted (not sent as empty strings). `amount` passes through untouched as a
 * string; `currency` is hard-coded to `"USD"` (not a form field).
 */
export function toCreateBody(values: SupplierPaymentFormValues): SupplierPaymentCreate {
  const t = (s: string) => s.trim();
  const opt = (s: string): string | undefined => (t(s) === '' ? undefined : t(s));

  return {
    swift_ref: t(values.swift_ref),
    payment_date: values.payment_date,
    amount: t(values.amount),
    currency: 'USD',
    payment_type: values.payment_type as SupplierPaymentCreate['payment_type'],
    bank_name: opt(values.bank_name),
    notes: opt(values.notes),
  };
}
