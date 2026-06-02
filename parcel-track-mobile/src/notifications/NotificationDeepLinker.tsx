/**
 * Wires the runtime push listeners that need the query client + router.
 *
 * Three subscriptions, all best-effort:
 *
 *  1. **Received-while-foreground.** Bumps the `['notifications']` query
 *     prefix so the Inbox tab list + the unread-count badge refresh. Same
 *     prefix the mark-read mutation hits — see `useMarkNotificationRead`.
 *
 *  2. **Tap (background → foreground).** Reads `data.booking_id` /
 *     `data.notification_id` off the response (shipped by the backend in
 *     `app/background/tasks.py` → `send_push_notification`). Deep-links to
 *     `/bookings/{id}` if present, else falls back to `/inbox` (where the
 *     notifications feed now lives — Phase 10), and PATCHes
 *     the mark-read endpoint via `authedApiRequest` (one fire-and-forget
 *     write; we're outside React render so we can't use the hook).
 *
 *  3. **Cold-launch from tap.** `addNotificationResponseReceivedListener`
 *     does NOT fire when the app is *launched* by the tap — only when an
 *     already-running app receives a tap. So we also pull
 *     `getLastNotificationResponseAsync()` once on mount and run the same
 *     handler if it returned non-null.
 *
 * Mounted inside `<AuthProvider>` so it can `useRouter` + `useQueryClient`.
 * It renders nothing.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import * as Notifications from 'expo-notifications';
import { useEffect, useRef } from 'react';

import { authedApiRequest } from '../api/authedClient';

type PushDataPayload = {
  booking_id?: string;
  notification_id?: string;
  type?: string;
};

function extractData(response: Notifications.NotificationResponse): PushDataPayload {
  const raw = response.notification.request.content.data;
  return (raw ?? {}) as PushDataPayload;
}

function markReadFireAndForget(notificationId: string | undefined): void {
  if (!notificationId) return;
  void authedApiRequest(`/api/v1/notifications/${notificationId}/read`, {
    method: 'PATCH',
  }).catch(() => {
    // Best-effort — the row is still reachable via Inbox and pull-to-refresh.
  });
}

export function NotificationDeepLinker(): null {
  const router = useRouter();
  const queryClient = useQueryClient();

  // Stash the handler in a ref so the effect can wire listeners once and the
  // cleanup uses the exact same Subscription objects, while the handler body
  // still closes over the latest router / queryClient via the ref.
  const handlerRef = useRef<(response: Notifications.NotificationResponse) => void>(() => {});
  handlerRef.current = (response) => {
    const data = extractData(response);
    markReadFireAndForget(data.notification_id);
    queryClient.invalidateQueries({ queryKey: ['notifications'] });
    if (data.booking_id) {
      router.push(`/bookings/${data.booking_id}`);
    } else {
      router.push('/inbox');
    }
  };

  // Foreground delivery: refresh lists + unread badge.
  useEffect(() => {
    const sub = Notifications.addNotificationReceivedListener(() => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    });
    return () => sub.remove();
  }, [queryClient]);

  // Tap (warm app).
  useEffect(() => {
    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      handlerRef.current(response);
    });
    return () => sub.remove();
  }, []);

  // Cold-launch from tap: the response listener doesn't fire for the launch
  // event itself, only for subsequent taps. Pull the last response once on
  // mount and replay it through the same handler.
  useEffect(() => {
    let cancelled = false;
    void Notifications.getLastNotificationResponseAsync().then((response) => {
      if (cancelled || !response) return;
      handlerRef.current(response);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
