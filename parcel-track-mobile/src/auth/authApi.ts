/**
 * Typed wrappers around /api/v1/auth/* endpoints.
 *
 * Keeps snake_case → camelCase translation in one place so the rest of the
 * app deals only in idiomatic TS shapes.
 */

import { apiRequest } from '../api/client';

interface RawTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

export async function loginRequest(email: string, password: string): Promise<TokenPair> {
  const raw = await apiRequest<RawTokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: { email, password },
    auth: 'skip',
  });
  return {
    accessToken: raw.access_token,
    refreshToken: raw.refresh_token,
  };
}

export async function refreshRequest(refreshToken: string): Promise<TokenPair> {
  const raw = await apiRequest<RawTokenResponse>('/api/v1/auth/refresh', {
    method: 'POST',
    body: { refresh_token: refreshToken },
    auth: 'skip',
  });
  return {
    accessToken: raw.access_token,
    refreshToken: raw.refresh_token,
  };
}
