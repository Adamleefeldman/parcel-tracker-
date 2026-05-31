/**
 * Notifications feed query.
 *
 * GET /api/v1/notifications?unread_only=&limit=&offset= → PaginatedResponse<NotificationOut>.
 * Role-scoped server-side (a user only sees their own rows).
 *
 * Query-key convention mirrors useBookings: resource name first, then a
 * stable-keyed filters object. The mark-read mutation invalidates the bare
 * `['notifications']` prefix, which matches every key here AND the
 * unread-count key — so one invalidation refetches the list and the badge.
 */

import { useQuery } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { NotificationOut } from '../types/notification';
import type { PaginatedResponse } from './useBookings';

export interface NotificationsFilters {
  unreadOnly?: boolean;
  limit?: number;
  offset?: number;
}

export function notificationsQueryKey(filters: NotificationsFilters = {}): readonly unknown[] {
  return ['notifications', filters] as const;
}

export function buildNotificationsPath(filters: NotificationsFilters): string {
  const params = new URLSearchParams();
  if (filters.unreadOnly !== undefined) params.set('unread_only', String(filters.unreadOnly));
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  return qs ? `/api/v1/notifications?${qs}` : '/api/v1/notifications';
}

export function useNotifications(filters: NotificationsFilters = {}) {
  return useQuery({
    queryKey: notificationsQueryKey(filters),
    queryFn: () =>
      authedApiRequest<PaginatedResponse<NotificationOut>>(buildNotificationsPath(filters)),
  });
}
