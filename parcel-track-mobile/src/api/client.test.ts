/**
 * Tests for the 401-driven refresh + retry flow in apiRequest.
 *
 * We mock the auth/* modules (refresh helper, session-expired emitter,
 * token storage) and global fetch so the test focuses on the logic in
 * client.ts itself. Each test resets the mocks before running so the
 * module-level single-flight gate doesn't leak across cases.
 */

jest.mock('../auth/authApi', () => ({
  refreshRequest: jest.fn(),
}));
jest.mock('../auth/sessionEvents', () => ({
  emitSessionExpired: jest.fn(),
}));
jest.mock('../auth/tokenStorage', () => ({
  getRefreshToken: jest.fn(),
  setTokens: jest.fn(),
  clearTokens: jest.fn(),
}));

import { apiRequest } from './client';
import { refreshRequest } from '../auth/authApi';
import { emitSessionExpired } from '../auth/sessionEvents';
import { clearTokens, getRefreshToken, setTokens } from '../auth/tokenStorage';

const mockRefresh = refreshRequest as jest.MockedFunction<typeof refreshRequest>;
const mockEmit = emitSessionExpired as jest.MockedFunction<typeof emitSessionExpired>;
const mockGetRefresh = getRefreshToken as jest.MockedFunction<typeof getRefreshToken>;
const mockSetTokens = setTokens as jest.MockedFunction<typeof setTokens>;
const mockClearTokens = clearTokens as jest.MockedFunction<typeof clearTokens>;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('apiRequest', () => {
  let fetchMock: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    fetchMock = jest.fn();
    (globalThis as { fetch: unknown }).fetch = fetchMock;
    mockGetRefresh.mockResolvedValue('stored-refresh-token');
    mockSetTokens.mockResolvedValue(undefined);
    mockClearTokens.mockResolvedValue(undefined);
  });

  it('passes through normally on 200', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    const result = await apiRequest<{ ok: boolean }>('/api/v1/anything', {
      accessToken: 'access-1',
    });

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('refreshes and retries on 401, returning the retried response', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { data: 'ok-after-refresh' }));
    mockRefresh.mockResolvedValueOnce({
      accessToken: 'new-access',
      refreshToken: 'new-refresh',
    });

    const result = await apiRequest<{ data: string }>('/api/v1/thing', {
      accessToken: 'stale-access',
    });

    expect(result).toEqual({ data: 'ok-after-refresh' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(mockRefresh).toHaveBeenCalledTimes(1);
    expect(mockRefresh).toHaveBeenCalledWith('stored-refresh-token');
    expect(mockSetTokens).toHaveBeenCalledWith({
      accessToken: 'new-access',
      refreshToken: 'new-refresh',
    });
    // Retry should carry the new bearer token, not the stale one.
    const retryHeaders = fetchMock.mock.calls[1][1].headers as Record<string, string>;
    expect(retryHeaders.Authorization).toBe('Bearer new-access');
    expect(mockEmit).not.toHaveBeenCalled();
  });

  it('does NOT loop: a 401 on the retried request surfaces as a 401, not another refresh', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'still bad' }));
    mockRefresh.mockResolvedValueOnce({
      accessToken: 'new-access',
      refreshToken: 'new-refresh',
    });

    await expect(
      apiRequest('/api/v1/thing', { accessToken: 'stale-access' }),
    ).rejects.toMatchObject({ status: 401, message: 'still bad' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(mockRefresh).toHaveBeenCalledTimes(1);
    expect(mockEmit).not.toHaveBeenCalled();
  });

  it('single-flights concurrent 401s: 5 parallel calls trigger exactly 1 refresh', async () => {
    // First 5 fetches all 401 (the original requests fired in parallel).
    // Next 5 fetches all succeed (the retries after the single refresh).
    for (let i = 0; i < 5; i++) {
      fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }));
    }
    for (let i = 0; i < 5; i++) {
      fetchMock.mockResolvedValueOnce(jsonResponse(200, { i }));
    }
    // Gate the refresh promise so all 5 callers are queued on it before it resolves.
    let resolveRefresh!: (v: { accessToken: string; refreshToken: string }) => void;
    mockRefresh.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRefresh = resolve;
        }),
    );

    const inFlight = Promise.all([
      apiRequest<{ i: number }>('/a', { accessToken: 'stale' }),
      apiRequest<{ i: number }>('/b', { accessToken: 'stale' }),
      apiRequest<{ i: number }>('/c', { accessToken: 'stale' }),
      apiRequest<{ i: number }>('/d', { accessToken: 'stale' }),
      apiRequest<{ i: number }>('/e', { accessToken: 'stale' }),
    ]);

    // Let the first round of fetches resolve to 401 and all 5 callers reach
    // refreshAccessToken — the first one starts a refresh, the other four
    // see refreshInFlight !== null and await it.
    await new Promise((r) => setImmediate(r));
    await new Promise((r) => setImmediate(r));

    resolveRefresh({ accessToken: 'new-access', refreshToken: 'new-refresh' });
    const results = await inFlight;

    expect(results).toHaveLength(5);
    expect(mockRefresh).toHaveBeenCalledTimes(1);
    expect(mockSetTokens).toHaveBeenCalledTimes(1);
    // 5 initial 401s + 5 retries = 10 fetches.
    expect(fetchMock).toHaveBeenCalledTimes(10);
  });

  it('does not attempt refresh when auth: "skip"', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: 'bad creds' }));

    await expect(
      apiRequest('/api/v1/auth/login', {
        method: 'POST',
        body: { email: 'a', password: 'b' },
        auth: 'skip',
      }),
    ).rejects.toMatchObject({ status: 401, message: 'bad creds' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(mockRefresh).not.toHaveBeenCalled();
    expect(mockClearTokens).not.toHaveBeenCalled();
    expect(mockEmit).not.toHaveBeenCalled();
  });

  it('on refresh failure clears tokens, emits session-expired, and surfaces the original 401', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }));
    // refresh helper itself throws — simulates refresh endpoint 401, network
    // error, missing refresh token, etc. apiRequest treats them all the same.
    mockRefresh.mockRejectedValueOnce(new Error('refresh token dead'));

    await expect(
      apiRequest('/api/v1/thing', { accessToken: 'stale-access' }),
    ).rejects.toMatchObject({ status: 401 });

    expect(mockClearTokens).toHaveBeenCalledTimes(1);
    expect(mockEmit).toHaveBeenCalledTimes(1);
    // Only the original request fired; no retry should be attempted.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
