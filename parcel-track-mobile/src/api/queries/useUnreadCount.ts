/**
 * Unread notification count for the Alerts tab badge.
 *
 * There is NO `/notifications/unread-count` endpoint, so we derive the count
 * from the paginated list's `total` with `unread_only=true&limit=1` — we only
 * need the count, not the rows.
 *
 * Key is `['notifications', 'unread-count']` — under the `['notifications']`
 * prefix so the mark-read mutation's prefix-invalidation refetches it.
 */

import { useQuery } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { NotificationOut } from '../types/notification';
import type { PaginatedResponse } from './useBookings';

export function unreadCountQueryKey(): readonly unknown[] {
  return ['notifications', 'unread-count'] as const;
}

export function useUnreadCount() {
  return useQuery({
    queryKey: unreadCountQueryKey(),
    queryFn: async () => {
      const res = await authedApiRequest<PaginatedResponse<NotificationOut>>(
        '/api/v1/notifications?unread_only=true&limit=1',
      );
      return res.total;
    },
  });
}
