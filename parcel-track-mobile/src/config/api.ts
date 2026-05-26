/**
 * API configuration.
 *
 * The base URL is injected at build time from EXPO_PUBLIC_API_URL.
 * Loading order:
 *   - dev  (`expo start`):    .env.development.local → .env.local → .env.development → .env
 *   - prod (`expo export`):   .env.production.local → .env.local → .env.production → .env
 *
 * For physical device testing, override in .env.local with your Mac's LAN IP
 * (e.g. http://192.168.x.x:8000). See AGENTS.md.
 */

const FALLBACK_API_URL = 'http://localhost:8000';

const envUrl = process.env.EXPO_PUBLIC_API_URL;

if (!envUrl && __DEV__) {
  // Warn loudly in dev if the env file wasn't picked up; in prod we silently fall back.
  // eslint-disable-next-line no-console
  console.warn(
    '[config/api] EXPO_PUBLIC_API_URL is not set — falling back to ' +
      `${FALLBACK_API_URL}. Check your .env files.`,
  );
}

export const API_BASE_URL: string = envUrl ?? FALLBACK_API_URL;
