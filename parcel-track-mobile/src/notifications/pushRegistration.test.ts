/**
 * Tests for the push-token registration helpers.
 *
 * Node-env jest: the real `expo-notifications` / `expo-device` modules can't
 * load — see `src/__mocks__/expo-notifications.ts` + `expo-device.ts` for
 * the stand-ins. We assert the URL shape (the route takes the token as a
 * **query param**) and that the helper goes through `authedApiRequest` so
 * the 401-refresh flow stays intact.
 */

jest.mock('../api/authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../api/authedClient';
import {
  __resetPushRegistrationForTests,
  buildPushTokenPath,
  registerAndSyncPushToken,
  sendTokenToServer,
} from './pushRegistration';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

describe('buildPushTokenPath', () => {
  it('encodes the token into a query param on /api/v1/notifications/push-token', () => {
    expect(buildPushTokenPath('ExponentPushToken[abc123]')).toBe(
      '/api/v1/notifications/push-token?token=ExponentPushToken%5Babc123%5D',
    );
  });

  it('round-trips arbitrary token characters without corruption', () => {
    const weird = 'tok&with=chars?and+plus space';
    expect(buildPushTokenPath(weird)).toBe(
      `/api/v1/notifications/push-token?token=${encodeURIComponent(weird)}`,
    );
  });
});

describe('sendTokenToServer', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('PATCHes the push-token endpoint with the encoded token as a query param', async () => {
    mockAuthedApiRequest.mockResolvedValue({ message: 'Push token registered' });

    await sendTokenToServer('ExponentPushToken[abc123]');

    expect(mockAuthedApiRequest).toHaveBeenCalledWith(
      '/api/v1/notifications/push-token?token=ExponentPushToken%5Babc123%5D',
      { method: 'PATCH' },
    );
  });
});

describe('registerAndSyncPushToken', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __resetPushRegistrationForTests();
  });

  it('fetches the Expo token and forwards it to the backend (happy path)', async () => {
    mockAuthedApiRequest.mockResolvedValue({ message: 'Push token registered' });

    await registerAndSyncPushToken();

    // The mock returns 'ExponentPushToken[stub]' from getExpoPushTokenAsync.
    expect(mockAuthedApiRequest).toHaveBeenCalledWith(
      '/api/v1/notifications/push-token?token=ExponentPushToken%5Bstub%5D',
      { method: 'PATCH' },
    );
  });

  it('swallows backend errors — push registration must never reject', async () => {
    mockAuthedApiRequest.mockRejectedValue(new Error('boom'));

    await expect(registerAndSyncPushToken()).resolves.toBeUndefined();
  });

  it('is idempotent within a session (second call is a no-op)', async () => {
    mockAuthedApiRequest.mockResolvedValue({ message: 'Push token registered' });

    await registerAndSyncPushToken();
    await registerAndSyncPushToken();

    expect(mockAuthedApiRequest).toHaveBeenCalledTimes(1);
  });
});
