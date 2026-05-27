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
