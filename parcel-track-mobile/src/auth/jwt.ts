/**
 * Client-side JWT payload decoding.
 *
 * The mobile app does NOT verify the signature — the backend does that on
 * every request. We only peek at the payload to surface user identity in the
 * UI without an extra round-trip (no /me endpoint exists yet).
 *
 * Swap this for a real /me fetch when the backend grows one — then we can
 * carry name/email too.
 */

import { jwtDecode } from 'jwt-decode';

export interface User {
  id: string;
  role: string;
}

interface AccessTokenPayload {
  sub?: unknown;
  role?: unknown;
  type?: unknown;
}

export function decodeUserFromToken(accessToken: string): User | null {
  let payload: AccessTokenPayload;
  try {
    payload = jwtDecode<AccessTokenPayload>(accessToken);
  } catch {
    return null;
  }
  if (typeof payload.sub !== 'string' || typeof payload.role !== 'string') {
    return null;
  }
  return { id: payload.sub, role: payload.role };
}
