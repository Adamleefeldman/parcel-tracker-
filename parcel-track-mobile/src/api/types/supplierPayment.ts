/**
 * Supplier-payment types — hand-typed mirrors of the backend schemas
 * (`app/schemas/schemas.py` → SupplierPaymentCreate / SupplierPaymentOut).
 *
 * Supplier payments are outbound USD wires against a purchase order's invoice
 * (money OUT — the mirror of Phase 4's inbound customer payments). They are
 * **invoice-scoped** and **admin-only** on both create and list.
 *
 * The Out shape is identical to the `SupplierPayment` already embedded in
 * `BookingDetailOut.payments`, so we reuse that type rather than redeclare it.
 * Only the create-request body is new here.
 *
 * Money discipline: `amount` is a `Decimal` server-side, serialized as a JSON
 * **string** (Pydantic model) — keep it a `string` end-to-end and never
 * float-parse it for submission. Masked fields (`amount`, `swift_ref`) come
 * back null for non-admins, but the whole feature is admin-gated so that's
 * not user-visible here.
 */

import type { SupplierPaymentType } from './enums';

// Re-export the Out shape (defined once, on the booking detail type).
export type { SupplierPayment } from './booking';

/**
 * `SupplierPaymentCreate` request body. `amount` stays a decimal string; the
 * server validates `amount > 0` (single-field rule only). Status is **server-
 * set** to `confirmed` — the client never sends it, and there is no separate
 * confirm step. Optional fields are omitted (not sent blank) when empty.
 */
export interface SupplierPaymentCreate {
  swift_ref: string;
  payment_date: string; // YYYY-MM-DD
  amount: string; // USD, decimal string
  currency: string; // always "USD" — no other currency is supported
  payment_type: SupplierPaymentType;
  bank_name?: string;
  notes?: string;
}
