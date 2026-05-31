/**
 * Presentation for notification rows: a human label + a pill tone per
 * NotificationType. The `Record<NotificationType, …>` shape fails the
 * typecheck if the backend adds a new enum value without a mapping here
 * (mirror the value into `enums.ts` first). notificationDisplay.test.ts
 * belt-and-braces this at runtime.
 */

import type { NotificationType } from '../../api/types/enums';
import type { PillTone } from '../../components/ui/Pill';

export const NOTIFICATION_LABELS: Record<NotificationType, string> = {
  po_submitted: 'PO submitted',
  invoice_received: 'Invoice received',
  payment_confirmed: 'Payment confirmed',
  bl_uploaded: 'BL uploaded',
  vessel_departed: 'Vessel departed',
  vessel_approaching: 'Vessel approaching',
  vessel_delayed: 'Vessel delayed',
  vessel_arrived: 'Vessel arrived',
  container_hold: 'Container on hold',
  container_cleared: 'Container cleared',
  clearing_docs_urgent: 'Clearing docs urgent',
  delivery_scheduled: 'Delivery scheduled',
  delivery_complete: 'Delivery complete',
  ar_aging_alert: 'Receivable overdue',
  demurrage_warning: 'Demurrage warning',
};

const NOTIFICATION_TONES: Record<NotificationType, PillTone> = {
  po_submitted: 'default',
  invoice_received: 'default',
  payment_confirmed: 'success',
  bl_uploaded: 'default',
  vessel_departed: 'default',
  vessel_approaching: 'default',
  vessel_delayed: 'warning',
  vessel_arrived: 'success',
  container_hold: 'warning',
  container_cleared: 'success',
  clearing_docs_urgent: 'warning',
  delivery_scheduled: 'default',
  delivery_complete: 'success',
  ar_aging_alert: 'error',
  demurrage_warning: 'error',
};

export function notificationLabel(type: NotificationType): string {
  return NOTIFICATION_LABELS[type] ?? 'Notification';
}

export function notificationTone(type: NotificationType): PillTone {
  return NOTIFICATION_TONES[type] ?? 'default';
}
