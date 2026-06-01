import type { NotificationType } from './enums';

/**
 * Mirrors `NotificationOut` (`parcel-track/app/schemas/schemas.py`). Note the
 * field is `message` (not `body`), and the only entity reference is
 * `booking_id` (nullable) — there is no `entity_type`/`entity_id`. So a
 * notification deep-links cleanly to a booking when `booking_id` is set, and is
 * mark-read-only otherwise.
 */
export interface NotificationOut {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  read: boolean;
  booking_id: string | null;
  created_at: string;
}
