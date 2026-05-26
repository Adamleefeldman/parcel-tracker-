/**
 * Minimal typed HTTP client.
 *
 * Wraps fetch with:
 *   - API_BASE_URL prefixing
 *   - JSON content negotiation
 *   - Bearer-token injection (caller supplies; this module is auth-agnostic)
 *   - Uniform error shape (ApiError) so callers don't branch on fetch internals
 *   - 401 → refresh → retry-once flow for normal (auth: 'normal') calls
 *
 * The 401 flow lives here, not in a wrapper layer, so every authenticated
 * caller automatically gets it. Auth-endpoint calls (login, refresh itself)
 * pass `auth: 'skip'` to opt out — a 401 from those means bad creds or a
 * dead refresh token, not "access token expired."
 */

import { refreshRequest } from '../auth/authApi';
import { emitSessionExpired } from '../auth/sessionEvents';
import { clearTokens, getRefreshToken, setTokens } from '../auth/tokenStorage';
import { API_BASE_URL } from '../config/api';

/** Default request timeout. Long enough for slow LTE, short enough not to hang the UI. */
const DEFAULT_TIMEOUT_MS = 15_000;

/** Sentinel status for non-HTTP failures (network down, timeout, DNS, TLS). */
export const NETWORK_ERROR_STATUS = 0;

export interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Bearer token. Omit for unauthenticated calls. */
  accessToken?: string;
  /** Additional headers (override defaults). */
  headers?: Record<string, string>;
  /** Override request timeout in ms. Defaults to 15 s. */
  timeoutMs?: number;
  /**
   * 'normal' (default): on 401, try one refresh + retry; on refresh failure,
   * clear tokens and emit a session-expired event.
   * 'skip': pass 401s straight through. Used by login + refresh themselves.
   */
  auth?: 'normal' | 'skip';
}

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }

  /** True when the failure was transport-level (no HTTP response received). */
  get isNetworkError(): boolean {
    return this.status === NETWORK_ERROR_STATUS;
  }
}

interface RawResponse {
  status: number;
  ok: boolean;
  parsed: unknown;
}

async function performRequest(
  path: string,
  method: string,
  body: unknown,
  accessToken: string | undefined,
  headers: Record<string, string>,
  timeoutMs: number,
): Promise<RawResponse> {
  const url = `${API_BASE_URL}${path}`;
  const finalHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...headers,
  };
  if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json';
  }
  if (accessToken) {
    finalHeaders.Authorization = `Bearer ${accessToken}`;
  }

  // Per-request abort controller for timeout. We don't accept an external signal
  // yet — add when a screen needs cancel-on-unmount.
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: finalHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    // Transport-level failure (DNS, TLS, offline) or our own AbortController timeout.
    // In React Native (Hermes) there is no DOMException global — aborted fetches
    // throw a plain Error with name === 'AbortError', and network failures throw
    // TypeError('Network request failed'). Map both into ApiError so callers see
    // one shape.
    const aborted = err instanceof Error && err.name === 'AbortError';
    const message = aborted
      ? 'Request timed out. Check your connection and try again.'
      : 'Network unavailable. Check your connection and try again.';
    throw new ApiError(NETWORK_ERROR_STATUS, message, err);
  } finally {
    clearTimeout(timeoutHandle);
  }

  // Parse body once. Try JSON; fall back to text for non-JSON error bodies.
  const rawText = await response.text();
  let parsed: unknown = null;
  if (rawText) {
    try {
      parsed = JSON.parse(rawText);
    } catch {
      parsed = rawText;
    }
  }

  return { status: response.status, ok: response.ok, parsed };
}

// Module-level single-flight gate. If 5 authenticated requests all 401 at
// the same time, we run exactly one refresh and the other 4 await its result.
let refreshInFlight: Promise<string> | null = null;

/**
 * Get a fresh access token, single-flighting concurrent refreshes.
 *
 * Returns the new access token. Throws on refresh failure (caller is
 * responsible for clearing tokens + emitting session-expired).
 */
async function refreshAccessToken(): Promise<string> {
  if (refreshInFlight) {
    return refreshInFlight;
  }
  refreshInFlight = (async () => {
    const stored = await getRefreshToken();
    if (!stored) {
      throw new Error('no refresh token stored');
    }
    const tokens = await refreshRequest(stored);
    await setTokens(tokens);
    return tokens.accessToken;
  })();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const {
    method = 'GET',
    body,
    accessToken,
    headers = {},
    timeoutMs = DEFAULT_TIMEOUT_MS,
    auth = 'normal',
  } = options;

  let result = await performRequest(path, method, body, accessToken, headers, timeoutMs);

  if (result.status === 401 && auth === 'normal') {
    // Access token is (likely) expired. Try one refresh + retry. Whatever
    // comes back from the retry is final — no second refresh, no loop.
    let newAccessToken: string;
    try {
      newAccessToken = await refreshAccessToken();
    } catch {
      // Refresh failed (refresh token dead, network down mid-refresh, etc.).
      // Tear down the session and let the original 401 propagate so the
      // caller still sees a real failure.
      await clearTokens();
      emitSessionExpired();
      throw new ApiError(
        result.status,
        extractErrorMessage(result.parsed, `Request failed: ${result.status}`),
        result.parsed,
      );
    }
    result = await performRequest(path, method, body, newAccessToken, headers, timeoutMs);
  }

  if (!result.ok) {
    const message = extractErrorMessage(result.parsed, `Request failed: ${result.status}`);
    throw new ApiError(result.status, message, result.parsed);
  }

  return result.parsed as T;
}

/**
 * Pull a human-readable message out of a FastAPI error body.
 *
 * Handles three shapes the backend returns:
 *   - `{ detail: "some string" }` — HTTPException(detail=...)
 *   - `{ detail: [{ msg, loc, type }, ...] }` — Pydantic 422 validation errors
 *   - anything else — fall through to caller-provided fallback
 *
 * We previously did `String(parsed.detail)` unconditionally, which collapsed
 * arrays/objects into the useless "[object Object]". Always extract a real
 * string before showing it to a user.
 */
function extractErrorMessage(parsed: unknown, fallback: string): string {
  if (!parsed || typeof parsed !== 'object' || !('detail' in parsed)) {
    return fallback;
  }
  const detail = (parsed as { detail: unknown }).detail;

  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    const msgs = detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg);
        }
        return null;
      })
      .filter((m): m is string => !!m);
    if (msgs.length > 0) {
      return msgs.join('; ');
    }
  }

  return fallback;
}
