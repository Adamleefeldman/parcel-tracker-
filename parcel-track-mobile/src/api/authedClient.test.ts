/**
 * Tests for the authed API wrapper.
 *
 * `authedApiRequest` is intentionally tiny — its only job is to pull the
 * access token out of SecureStore and forward everything else to `apiRequest`.
 * The 401 → refresh → retry flow has its own coverage in client.test.ts; we
 * do NOT re-test that here.
 */

jest.mock('../auth/tokenStorage', () => ({
  getAccessToken: jest.fn(),
}));
jest.mock('./client', () => ({
  apiRequest: jest.fn(),
}));

import { authedApiRequest } from './authedClient';
import { getAccessToken } from '../auth/tokenStorage';
import { apiRequest } from './client';

const mockGetAccessToken = getAccessToken as jest.MockedFunction<typeof getAccessToken>;
const mockApiRequest = apiRequest as jest.MockedFunction<typeof apiRequest>;

describe('authedApiRequest', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('passes the stored access token through to apiRequest', async () => {
    mockGetAccessToken.mockResolvedValue('token-abc');
    mockApiRequest.mockResolvedValue({ ok: true });

    await authedApiRequest('/api/v1/anything');

    expect(mockGetAccessToken).toHaveBeenCalledTimes(1);
    expect(mockApiRequest).toHaveBeenCalledWith('/api/v1/anything', {
      accessToken: 'token-abc',
    });
  });

  it('forwards method, body, headers, and timeout untouched', async () => {
    mockGetAccessToken.mockResolvedValue('token-xyz');
    mockApiRequest.mockResolvedValue(undefined);

    await authedApiRequest('/api/v1/thing', {
      method: 'POST',
      body: { a: 1 },
      headers: { 'X-Trace': 'abc' },
      timeoutMs: 5000,
    });

    expect(mockApiRequest).toHaveBeenCalledWith('/api/v1/thing', {
      method: 'POST',
      body: { a: 1 },
      headers: { 'X-Trace': 'abc' },
      timeoutMs: 5000,
      accessToken: 'token-xyz',
    });
  });

  it('passes accessToken: undefined when no token is stored', async () => {
    // apiRequest's own 401-refresh flow handles the "missing token" case
    // (it will fire the request unauthenticated, get 401, attempt refresh,
    // fail because there is no refresh token, and emit session-expired).
    mockGetAccessToken.mockResolvedValue(null);
    mockApiRequest.mockResolvedValue(null);

    await authedApiRequest('/api/v1/thing');

    expect(mockApiRequest).toHaveBeenCalledWith('/api/v1/thing', {
      accessToken: undefined,
    });
  });

  it('returns the value from apiRequest unchanged', async () => {
    mockGetAccessToken.mockResolvedValue('t');
    mockApiRequest.mockResolvedValue({ total: 2, items: [{ id: '1' }] });

    const result = await authedApiRequest<{ total: number; items: { id: string }[] }>(
      '/api/v1/bookings',
    );

    expect(result).toEqual({ total: 2, items: [{ id: '1' }] });
  });
});
