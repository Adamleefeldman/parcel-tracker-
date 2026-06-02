/**
 * Push-notification registration helpers.
 *
 * Flow:
 *   1. Caller (AuthProvider on signIn + cold-start) invokes
 *      `registerAndSyncPushToken` fire-and-forget. Never blocks the login UX.
 *   2. We ask the OS for permission (once). On denial, return null and stop —
 *      no nagging, no banner; the in-app Alerts tab still works.
 *   3. On grant, ask Expo for the device's Expo push token, then PATCH it to
 *      the backend via `authedApiRequest`. Server overwrites last-write-wins,
 *      so re-registering is a safe no-op.
 *
 * The backend's `PATCH /api/v1/notifications/push-token?token=…` takes the
 * token as a **query param** (not a body) — see
 * `parcel-track/app/api/routes/notifications.py`. `buildPushTokenPath` is
 * extracted as a pure helper so the URL shape is unit-testable without
 * mocking the native bridge.
 *
 * `projectId` (for `getExpoPushTokenAsync`) is read from
 * `Constants.expoConfig.extra.eas.projectId`, populated by `eas init` in the
 * upcoming EAS phase. Pre-EAS / Expo Go works fine without it.
 */

import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { authedApiRequest } from '../api/authedClient';

// Module-scope guard so concurrent cold-start + signIn fires don't run twice
// in the same session. Best-effort — a new cold-start resets it naturally.
let registered = false;

export function buildPushTokenPath(token: string): string {
  return `/api/v1/notifications/push-token?token=${encodeURIComponent(token)}`;
}

export async function sendTokenToServer(token: string): Promise<void> {
  await authedApiRequest(buildPushTokenPath(token), { method: 'PATCH' });
}

export async function setupAndroidChannel(): Promise<void> {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync('default', {
    name: 'Default',
    importance: Notifications.AndroidImportance.MAX,
  });
}

export async function registerForPushNotificationsAsync(): Promise<string | null> {
  // Simulators / web don't get real push tokens; Expo recommends bailing.
  if (!Device.isDevice) return null;

  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== 'granted') {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== 'granted') return null;

  // Pre-EAS the value is undefined; SDK 54 accepts that for Expo Go. After
  // `eas init` it's mandatory for production builds — read it through.
  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ??
    (Constants as unknown as { easConfig?: { projectId?: string } }).easConfig?.projectId;

  const tokenResponse = await Notifications.getExpoPushTokenAsync(
    projectId ? { projectId } : undefined,
  );
  return tokenResponse.data;
}

/**
 * One-shot wrapper used by AuthProvider. Idempotent within a session (guarded
 * by the module-scope flag); always safe to call. Errors are swallowed —
 * push is a delivery-channel optimisation, never block sign-in on it.
 */
export async function registerAndSyncPushToken(): Promise<void> {
  if (registered) return;
  try {
    await setupAndroidChannel();
    const token = await registerForPushNotificationsAsync();
    if (token) {
      await sendTokenToServer(token);
      registered = true;
    }
  } catch {
    // Fire-and-forget: deliberate silence. The Alerts tab still works without push.
  }
}

/** Test-only — reset the module-scope guard so each test starts fresh. */
export function __resetPushRegistrationForTests(): void {
  registered = false;
}
