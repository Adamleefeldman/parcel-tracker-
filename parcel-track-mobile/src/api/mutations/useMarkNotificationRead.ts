/**
 * Mark a notification read.
 *
 * PATCH /api/v1/notifications/{id}/read (no body) → { message }. Note this is
 * PATCH, not POST. There is no bulk mark-all-read endpoint, so callers mark
 * one id at a time.
 *
 * onSuccess invalidates the bare `['notifications']` prefix — a single call
 * refetches every notifications list query AND the unread-count badge
 * (`['notifications', 'unread-count']`), both of which sit under that prefix.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      authedApiRequest<{ message: string }>(`/api/v1/notifications/${notificationId}/read`, {
        method: 'PATCH',
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  });
}
