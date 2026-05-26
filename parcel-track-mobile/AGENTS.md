# Project notes for AI agents

## Expo HAS CHANGED

Read the exact versioned docs at https://docs.expo.dev/versions/v54.0.0/ before writing any code.

(We're pinned to SDK 54 because Expo Go in the App Store was lagging the SDK 56 release at bootstrap time. Bump with `npx expo install expo@latest --fix` once a matching Expo Go is available, then update this link.)

## API base URL

Configured via `EXPO_PUBLIC_API_URL` env var. Loaded from `.env` (dev) or `.env.production` (prod builds). Consume via `import { API_BASE_URL } from '@/src/config/api'` — never hardcode URLs in components.

Production: `https://api.thefmcghub.com`.

## Physical device testing (LAN IP gotcha)

On the iOS Simulator or Android Emulator, `localhost` resolves to your Mac and the local backend works.

On a physical phone running Expo Go, `localhost` resolves to the phone itself — the backend is unreachable. Workaround: create `.env.local` (gitignored) with your Mac's LAN IP:

```
EXPO_PUBLIC_API_URL=http://192.168.x.x:8000
```

Find the IP with `ipconfig getifaddr en0`. Restart `expo start` after creating/changing `.env.local` — env files are read at bundler startup, not hot-reloaded.

## No browser globals

TypeScript's DOM lib is loaded by default, which silently allows things like `DOMException`, `localStorage`, `window`, `document`, `XMLHttpRequest`, `Blob`, etc. to typecheck. **None of these exist in React Native / Hermes** and referencing them is a runtime ReferenceError. Use `instanceof Error && err.name === 'AbortError'` instead of `instanceof DOMException`, `expo-secure-store` instead of `localStorage`, and so on.

## Auth & secrets

JWTs go in `expo-secure-store`, NEVER `AsyncStorage`. Tokens are credentials, treat them like passwords.

## CI

A single workflow at `../.github/workflows/ci.yml` (monorepo root) runs `npm ci` + `npx tsc --noEmit` as the `mobile-typecheck` job on every push/PR touching this directory. No tests, no lint yet — add when there's a real test suite or a style we want enforced. Run locally with `npx tsc --noEmit` to catch failures before pushing.

Caveat: a workflow trigger runs ALL jobs (backend + mobile), so a mobile-only PR still runs the backend pytest job (and vice versa). Inefficient but simpler than per-job path filtering. Acceptable cost at this scale.

## Deferred fixes (apply when adding the first authenticated screen)

Bootstrap login works, but the following are intentionally NOT yet implemented. The next agent/PR that touches authenticated calls should land them together:

1. **401-driven refresh-token flow.** When the access token expires (~15 min default), authenticated calls will fail and the user is silently stuck. Wire an interceptor in `src/api/client.ts` that, on 401, calls `POST /api/v1/auth/refresh` with the stored refresh token, persists the new pair via `setTokens()`, and retries the original request once. On refresh failure, call `clearTokens()` and flip auth status to `anonymous`.
2. **Cold-start token validation.** `AuthContext` currently trusts whatever token is in SecureStore on boot. With the refresh flow above in place, the first authenticated call (e.g. `GET /api/v1/users/me`) will self-heal — no separate boot validation needed.
3. **Cache user identity in `AuthContext`.** Once `/me` exists in the bootstrap flow, store the user object (id, email, name, role) in context so screens don't refetch. Currently only tokens are stored.
4. **Nav library.** Adopt Expo Router once we have ≥3 screens or need deep linking. Until then, conditional render in `App.tsx` is sufficient.

## Known `npm audit` noise

`npm audit` reports 10 moderate vulnerabilities, all transitively from `uuid < 11.1.1` ([GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq)). Path: `uuid → xcode → @expo/config-plugins → … → expo`.

**Do not run `npm audit fix --force`** — it downgrades `expo` ~10 major versions and breaks everything. The vulnerable code is build-time only (`xcode` package, used during `expo prebuild`/EAS Build); it does not ship in the app bundle and no attacker-controlled input reaches it. Wait for upstream `xcode`/Expo to bump `uuid`.
