/**
 * Minimal typed HTTP client.
 *
 * Wraps fetch with:
 *   - API_BASE_URL prefixing
 *   - JSON content negotiation
 *   - Bearer-token injection (caller supplies; this module is auth-agnostic)
 *   - Uniform error shape (ApiError) so callers don't branch on fetch internals
 */

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

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { method = 'GET', body, accessToken, headers = {}, timeoutMs = DEFAULT_TIMEOUT_MS } =
    options;

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

  if (!response.ok) {
    const message = extractErrorMessage(parsed, `Request failed: ${response.status}`);
    throw new ApiError(response.status, message, parsed);
  }

  return parsed as T;
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
