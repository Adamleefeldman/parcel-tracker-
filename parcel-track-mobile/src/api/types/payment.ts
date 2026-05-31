/**
 * Customer payment types — hand-typed mirrors of the backend schemas
 * (`app/schemas/schemas.py` → CustomerPaymentCreate / CustomerPaymentOut and
 * the aggregate route in `app/api/routes/customer_payments.py`).
 *
 * Money discipline: every amount is a `Decimal` on the server. The
 * Out/Create shapes serialize Decimals as JSON **strings** (Pydantic models),
 * so they're `string` here and we never float-parse them for submission.
 *
 * DRIFT from the planning doc: the aggregate endpoint returns a plain dict
 * (no `response_model`), so FastAPI's `jsonable_encoder` serializes its
 * Decimal totals as JSON **numbers**, not strings. `CustomerPaymentAggregate`
 * therefore types them as `number`. They're display-only (progress bar +
 * formatted totals) and never round-trip back to the server, so this doesn't
 * breach the strings-end-to-end rule for the submitted body.
 */

import type { CustomerPaymentMethod } from './enums';

/**
 * `CustomerPaymentOut`. Financial fields are **null for non-admins** (the
 * server masks them), so every money field is `string | null` — render the
 * null case as "—".
 */
export interface CustomerPayment {
  id: string;
  container_id: string;
  payment_date: string; // YYYY-MM-DD
  method: CustomerPaymentMethod;
  amount_received: string | null;
  variance: string | null;
  expense_courier: string | null;
  expense_bank_charge: string | null;
  banked_total: string | null;
  sender_bank: string | null;
  receiver_bank: string | null;
  tranche_index: number;
  customer_invoice_ref: string | null;
  notes: string | null;
  created_at: string;
}

/**
 * `CustomerPaymentCreate` request body. Amounts stay as decimal strings; the
 * server validates `amount_received > 0`, expenses `>= 0`, `tranche_index >= 1`
 * (single-field rules only — no cross-field validation). Optional fields are
 * omitted (not sent as empty strings) when blank.
 */
export interface CustomerPaymentCreate {
  payment_date: string; // YYYY-MM-DD
  method: CustomerPaymentMethod;
  amount_received: string;
  variance?: string;
  expense_courier?: string;
  expense_bank_charge?: string;
  banked_total?: string;
  sender_bank?: string;
  receiver_bank?: string;
  tranche_index?: number;
  customer_invoice_ref?: string;
  notes?: string;
}

/**
 * Aggregate totals across all tranches for a container. Numbers (see DRIFT
 * note above), display-only.
 */
export interface CustomerPaymentAggregate {
  total_received: number;
  total_variance: number;
  total_expenses: number;
  total_banked: number;
  tranche_count: number;
}
