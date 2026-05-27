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

### 401 → refresh → retry flow

Authenticated calls go through `apiRequest` (`src/api/client.ts`). On a 401, it:

1. Calls `POST /api/v1/auth/refresh` with the stored refresh token (single-flighted — N concurrent 401s do exactly one refresh).
2. On refresh success, persists the new pair via `setTokens()` and retries the original request once with the new access token.
3. On refresh failure (any non-2xx, network error, missing refresh token), calls `clearTokens()` and emits a `sessionExpired` event via `src/auth/sessionEvents.ts`. `AuthProvider` listens and flips status → `anonymous`, which renders `LoginScreen`.

The retried request is final — a second 401 surfaces as a 401; we never loop. Auth-endpoint calls (login, refresh itself) pass `auth: 'skip'` to opt out of the interceptor — a 401 there means bad creds / dead refresh token and must propagate as-is.

### Cached user identity

`AuthContext` exposes a `user: { id, role } | null` derived by decoding the access token's payload client-side (`src/auth/jwt.ts`, `jwt-decode`). Signature verification is the backend's job — the client only reads claims for UI.

When the backend grows a `/me` endpoint, swap `decodeUserFromToken` for a real fetch and extend the `User` type with `name` + `email`. The cold-start path can also become a real `/me` call at that point (currently lazy — we trust the SecureStore token on boot and let the first authenticated screen self-heal via the 401 flow above).

## CI

A single workflow at `../.github/workflows/ci.yml` (monorepo root) runs two mobile jobs on every push/PR touching this directory:

- `mobile-typecheck` — `npm ci` + `npx tsc --noEmit`
- `mobile-test` — `npm ci` + `npm test` (jest, ts-jest preset, node env; pure-logic tests only)

No lint yet — add when there's a style we want enforced. Run locally with `npx tsc --noEmit` and `npm test` to catch failures before pushing.

Caveat: a workflow trigger runs ALL jobs (backend + mobile), so a mobile-only PR still runs the backend pytest job (and vice versa). Inefficient but simpler than per-job path filtering. Acceptable cost at this scale.

## Navigation

File-based routing via **Expo Router** (`app/` directory). The root `app/_layout.tsx` wires the three top-level providers in this order: `QueryClientProvider` → `SafeAreaProvider` → `AuthProvider` → `<Slot/>`.

Two route groups, each with its own redirect-based guard:

- `app/(auth)/` — login + future auth screens. Layout redirects to `/(authed)` when `status === 'authenticated'`.
- `app/(authed)/` — every screen behind the login wall. Layout redirects to `/(auth)/login` when `status !== 'authenticated'`.

Route groups (`(name)`) don't appear in URLs but scope layouts, so the guard logic lives in one place per group, not on every screen. `status === 'loading'` short-circuits both guards to a `<Spinner centered />` so the cold-start flash doesn't ping-pong.

Navigation: `import { useRouter } from 'expo-router'` and `router.push('/(authed)/bookings/[id]')` — file paths, not screen names.

## Server state

All data fetching goes through **TanStack Query** hooks living in `src/api/queries/`. The `QueryClient` lives in the root layout with `staleTime: 30s`, `retry: 1`, `refetchOnWindowFocus: true`.

Hooks call `authedApiRequest` (`src/api/authedClient.ts`), NOT `apiRequest` directly. The wrapper pulls the access token from SecureStore so the 401-refresh flow in `apiRequest` has something to expire. Use `apiRequest` directly only for auth-skipping calls (login, refresh).

Query-key convention — always an array, resource name first, stable-keyed filters object second:

```ts
['bookings', { status, date_from, date_to, page }]
['bookings', id]
['containers', { booking_id }]
```

`bookings/index.tsx` is the reference implementation: pull-to-refresh wired to `refetch`, error state with retry button, empty state, list of `<ListItem>` + `<Pill>`.

## UI primitives

`src/components/ui/` holds the in-repo design system. `src/theme/tokens.ts` is the single source of truth for colors, spacing, typography, and radii. Components: `Text`, `Button`, `Input`, `Card`, `ListItem`, `Pill`, `ScreenContainer`, `Spinner`.

**Extend the tokens, then add a component — don't inline `StyleSheet` in screens.** Screens should only use primitives + token-derived layout values (`spacing.lg`, etc.). When a token isn't enough, the answer is usually a new primitive, not a one-off color literal.

No theme provider yet (single light theme). When dark mode lands, swap `tokens.ts` for a context-driven palette but keep the export names stable.

## Peer-dep noise

`.npmrc` sets `legacy-peer-deps=true` because Expo SDK 54 pins `react@19.1.0` while transitive deps (e.g. `react-dom@19.2.6` from `expo-router`) demand `react@^19.2.6`. The graph still resolves — Expo runs `npm install --legacy-peer-deps` under the hood for `npx expo install`, and CI's `npm ci` inherits the flag from `.npmrc`. Revisit when Expo unpins react.

## Known `npm audit` noise

`npm audit` reports 10 moderate vulnerabilities, all transitively from `uuid < 11.1.1` ([GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq)). Path: `uuid → xcode → @expo/config-plugins → … → expo`.

**Do not run `npm audit fix --force`** — it downgrades `expo` ~10 major versions and breaks everything. The vulnerable code is build-time only (`xcode` package, used during `expo prebuild`/EAS Build); it does not ship in the app bundle and no attacker-controlled input reaches it. Wait for upstream `xcode`/Expo to bump `uuid`.
