/**
 * In-memory stand-in for expo-notifications under jest (node env).
 *
 * The real module loads the Expo native bridge; importing it under node
 * crashes. This mock satisfies the surface area we touch in unit tests —
 * `pushRegistration.test.ts` — and nothing more. The listener / cold-start
 * APIs are only exercised at runtime via device verification (see Phase 8
 * plan), so they're stubbed to no-ops.
 */

export const AndroidImportance = {
  MIN: 1,
  LOW: 2,
  DEFAULT: 3,
  HIGH: 4,
  MAX: 5,
} as const;

export async function getPermissionsAsync(): Promise<{ status: string; granted: boolean }> {
  return { status: 'granted', granted: true };
}

export async function requestPermissionsAsync(): Promise<{ status: string; granted: boolean }> {
  return { status: 'granted', granted: true };
}

export async function getExpoPushTokenAsync(_options?: {
  projectId?: string;
}): Promise<{ data: string }> {
  return { data: 'ExponentPushToken[stub]' };
}

export async function setNotificationChannelAsync(
  _channelId: string,
  _channel: Record<string, unknown>,
): Promise<null> {
  return null;
}

export function setNotificationHandler(
  _handler: { handleNotification: () => Promise<unknown> } | null,
): void {
  // no-op
}

export function addNotificationReceivedListener(_listener: (event: unknown) => void): {
  remove: () => void;
} {
  return { remove: () => undefined };
}

export function addNotificationResponseReceivedListener(_listener: (event: unknown) => void): {
  remove: () => void;
} {
  return { remove: () => undefined };
}

export async function getLastNotificationResponseAsync(): Promise<null> {
  return null;
}
