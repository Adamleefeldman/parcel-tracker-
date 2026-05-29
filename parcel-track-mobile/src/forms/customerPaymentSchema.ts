/**
 * Validation schema for the record-customer-payment form (react-hook-form +
 * zod — the standard for non-trivial forms; see AGENTS.md → Forms).
 *
 * Money discipline: every amount stays a **string** through the form and into
 * the request body. The schema validates the string's *shape* (decimal regex,
 * positivity by lexical digit check) without ever parsing to float — a float
 * round-trip would corrupt the value. `tranche_index` is a count, not money,
 * so it converts to a number in `toCreateBody`.
 *
 * Mirrors only the backend's single-field rules (`CustomerPaymentCreate`):
 * `amount_received > 0`, expenses + `banked_total >= 0`, `tranche_index >= 1`.
 * There is no cross-field server validation, so none here either.
 */

import { z } from 'zod';

import { DECIMAL_RE, SIGNED_DECIMAL_RE } from '../lib/money';
import type { CustomerPaymentCreate } from '../api/types/payment';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Optional unsigned decimal field: a valid amount, or blank (= not provided). */
const optionalDecimal = (message: string) =>
  z.string().regex(DECIMAL_RE, message).or(z.literal(''));

export const customerPaymentSchema = z.object({
  payment_date: z.string().regex(DATE_RE, 'Pick a date'),
  // Select starts blank; refine rather than z.enum so the value type stays a
  // plain string (so the '' default validates as "not chosen yet"). The
  // `.includes` form is deliberate — a `v === 'cash' || v === 'transfer'`
  // predicate would be inferred as a type guard (TS 5.5+) and narrow the
  // inferred type to the union, rejecting the '' default value.
  method: z
    .string()
    .refine((v) => ['cash', 'transfer'].includes(v), 'Select a payment method'),
  amount_received: z
    .string()
    .regex(DECIMAL_RE, 'Enter a valid amount (up to 2 decimals)')
    .refine((v) => /[1-9]/.test(v), 'Amount must be greater than zero'),
  variance: z.string().regex(SIGNED_DECIMAL_RE, 'Enter a valid amount').or(z.literal('')),
  expense_courier: optionalDecimal('Enter a valid amount'),
  expense_bank_charge: optionalDecimal('Enter a valid amount'),
  banked_total: optionalDecimal('Enter a valid amount'),
  sender_bank: z.string().max(200, 'Too long (max 200)'),
  receiver_bank: z.string().max(200, 'Too long (max 200)'),
  tranche_index: z
    .string()
    .regex(/^\d+$/, 'Whole number')
    .refine((v) => /[1-9]/.test(v), 'Must be at least 1'),
  customer_invoice_ref: z.string().max(100, 'Too long (max 100)'),
  notes: z.string(),
});

/** All-string form values (RHF state). Mapped to the body via `toCreateBody`. */
export type CustomerPaymentFormValues = z.infer<typeof customerPaymentSchema>;

/** Today as `YYYY-MM-DD` in local time — the default payment date. */
export function todayIso(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

export const defaultPaymentFormValues: CustomerPaymentFormValues = {
  payment_date: todayIso(),
  method: '',
  amount_received: '',
  variance: '',
  expense_courier: '',
  expense_bank_charge: '',
  banked_total: '',
  sender_bank: '',
  receiver_bank: '',
  tranche_index: '1',
  customer_invoice_ref: '',
  notes: '',
};

/**
 * Map validated form values to the request body. Blank optional fields are
 * omitted (not sent as empty strings). Money values pass through untouched as
 * strings; `tranche_index` (a count) becomes a number. Bank fields are dropped
 * for non-transfer methods (the form hides them, but be defensive).
 */
export function toCreateBody(values: CustomerPaymentFormValues): CustomerPaymentCreate {
  const t = (s: string) => s.trim();
  const opt = (s: string): string | undefined => (t(s) === '' ? undefined : t(s));
  const isTransfer = values.method === 'transfer';

  return {
    payment_date: values.payment_date,
    method: values.method as CustomerPaymentCreate['method'],
    amount_received: t(values.amount_received),
    variance: opt(values.variance),
    expense_courier: opt(values.expense_courier),
    expense_bank_charge: opt(values.expense_bank_charge),
    banked_total: opt(values.banked_total),
    sender_bank: isTransfer ? opt(values.sender_bank) : undefined,
    receiver_bank: isTransfer ? opt(values.receiver_bank) : undefined,
    tranche_index: Number(t(values.tranche_index)),
    customer_invoice_ref: opt(values.customer_invoice_ref),
    notes: opt(values.notes),
  };
}
