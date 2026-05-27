/**
 * Authenticated API request wrapper.
 *
 * Pulls the current access token from SecureStore and forwards everything else
 * to `apiRequest`. The 401 → refresh → retry-once flow lives in `apiRequest`,
 * so this wrapper is only responsible for token plumbing.
 *
 * Every query / mutation hook should call this, NOT `apiRequest` directly,
 * unless the call is auth-skipping (login, refresh).
 */

import { getAccessToken } from '../auth/tokenStorage';
import { apiRequest, type ApiRequestOptions } from './client';

export async function authedApiRequest<T>(
  path: string,
  options: Omit<ApiRequestOptions, 'accessToken' | 'auth'> = {},
): Promise<T> {
  const accessToken = (await getAccessToken()) ?? undefined;
  return apiRequest<T>(path, { ...options, accessToken });
}
