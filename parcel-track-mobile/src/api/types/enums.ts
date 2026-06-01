/**
 * Mirror of the backend's string enums (`app/core/enums.py`).
 *
 * Hand-typed by design — codegen would be overkill at this scale. When the
 * backend adds a new value to one of these enums, this file must be updated
 * in the same PR; `StatusPill` exhaustively maps each member, so TS will
 * flag the gap at compile time.
 */

export type UserRole = 'admin' | 'morocco_agent' | 'uk_agent' | 'customer';

export type BookingStatus =
  | 'draft'
  | 'po_submitted'
  | 'invoice_received'
  | 'payment_confirmed'
  | 'bl_issued'
  | 'in_transit'
  | 'cleared'
  | 'complete';

export type ContainerStatus =
  | 'created'
  | 'vessel_assigned'
  | 'in_transit'
  | 'awaiting_customs'
  | 'on_hold'
  | 'cleared'
  | 'delivery_scheduled'
  | 'delivered';

export type ContainerLifecycleStatus =
  | 'ordered'
  | 'at_sea'
  | 'arrived'
  | 'import_cleared'
  | 'delivered'
  | 'invoiced'
  | 'paid'
  | 'banked'
  | 'closed'
  | 'disputed';

export type PortStatus =
  | 'not_arrived'
  | 'awaiting_customs'
  | 'customs_hold'
  | 'released';

/**
 * Inbound customer payment method. The backend has no `CustomerPaymentStatus`
 * enum — a payment row is valid on creation — so this is the only payment
 * enum to mirror (`CustomerPaymentCreate.method`, validated server-side).
 */
export type CustomerPaymentMethod = 'cash' | 'transfer';

/**
 * Entity a document attaches to (`DocumentEntityType` in `app/core/enums.py`).
 * A document is scoped to one sub-entity of a booking by `(entity_type,
 * entity_id)`. `DOCUMENT_ENTITY_LABELS` maps each member exhaustively (the
 * `Record<DocumentEntityType, …>` fails the typecheck if the backend adds a
 * value without a label here) — keep both in sync.
 */
export type DocumentEntityType =
  | 'purchase_order'
  | 'invoice'
  | 'payment'
  | 'bill_of_lading'
  | 'clearing_docs'
  | 'delivery_schedule';

export const DOCUMENT_ENTITY_LABELS: Record<DocumentEntityType, string> = {
  purchase_order: 'Purchase order',
  invoice: 'Invoice',
  payment: 'Payment',
  bill_of_lading: 'Bill of lading',
  clearing_docs: 'Clearing docs',
  delivery_schedule: 'Delivery schedule',
};

/**
 * In-app notification kind (`NotificationType` in `app/core/enums.py`). 15
 * values — keep this in sync; `NOTIFICATION_LABELS`/`NOTIFICATION_TONES`
 * (`src/features/alerts/notificationDisplay.ts`) map each member exhaustively,
 * so a new backend value fails the typecheck until it's added here too.
 */
export type NotificationType =
  | 'po_submitted'
  | 'invoice_received'
  | 'payment_confirmed'
  | 'bl_uploaded'
  | 'vessel_departed'
  | 'vessel_approaching'
  | 'vessel_delayed'
  | 'vessel_arrived'
  | 'container_hold'
  | 'container_cleared'
  | 'clearing_docs_urgent'
  | 'delivery_scheduled'
  | 'delivery_complete'
  | 'ar_aging_alert'
  | 'demurrage_warning';
