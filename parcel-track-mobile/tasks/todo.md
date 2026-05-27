# Phase 1 — mobile foundation + bookings list

Branch: `mobile-phase1-foundation`. Plan: `/Users/adamfeldman/.claude/plans/lets-construct-a-plan-synthetic-moon.md`.

## Step 1 — Expo Router migration
- [x] `npx expo install expo-router react-native-safe-area-context react-native-screens`
- [x] `package.json` → `"main": "expo-router/entry"`
- [x] `app.json` → add `expo.scheme: "fmcghub"` + `expo-router` plugin
- [x] `tsconfig.json` → `baseUrl` + `@/*` paths
- [x] Delete `App.tsx`, `index.ts`
- [x] Create `app/_layout.tsx` (providers)
- [x] `app/(auth)/_layout.tsx` (redirect when authed)
- [x] `app/(auth)/login.tsx` (port `LoginScreen`)
- [x] `app/(authed)/_layout.tsx` (redirect when anon)
- [x] `app/(authed)/index.tsx` (redirect to /bookings)
- [x] `app/(authed)/bookings/index.tsx`
- [x] `app/(authed)/bookings/[id].tsx`
- [x] Delete `src/screens/`
- [x] `npx tsc --noEmit` clean

## Step 2 — Design primitives
- [x] `src/theme/tokens.ts` + `index.ts`
- [x] 8 UI primitives in `src/components/ui/`
- [x] `src/components/ui/index.ts` barrel
- [x] Refactor `login.tsx` to use them
- [x] `npx tsc --noEmit` clean

## Step 3 — TanStack Query
- [x] `npm install @tanstack/react-query` (via `--legacy-peer-deps`; `.npmrc` pins it for CI)
- [x] `QueryClientProvider` in `app/_layout.tsx`
- [x] `src/api/authedClient.ts` wrapper
- [x] `src/api/queries/useBookings.ts`
- [x] `npx tsc --noEmit` clean

## Step 4 — Bookings list
- [x] Build `bookings/index.tsx` (FlatList, refresh, error, empty)
- [x] `bookings/[id].tsx` detail placeholder
- [x] `npx tsc --noEmit` clean

## Step 5 — Tests + docs
- [x] `src/api/authedClient.test.ts`
- [x] `src/api/queries/useBookings.test.ts`
- [x] `npm test` clean (4 suites / 16 tests)
- [x] Update `AGENTS.md` (Navigation / Server state / UI primitives / drop "Nav library" / `.npmrc` note)

## Ship
- [ ] Commit + push branch
- [ ] `gh pr create`
- [ ] Wait for CI green
