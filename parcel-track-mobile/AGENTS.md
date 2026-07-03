# AGENTS.md — parcel-track-mobile

_Last reviewed: 2026-06-12 (Phase 11 — UX polish & design-system hardening; lands after 13b). The Expo SDK pin and any "current state" notes below go stale fast — update this date whenever you touch them._

The companion backend doc is [`../parcel-track/CLAUDE.md`](../parcel-track/CLAUDE.md). Read it before doing anything that crosses the API boundary (auth shape, status enums, endpoint paths under `/api/v1`, error envelope).

---

## Core Principles

- Simplicity first. Senior-dev standards. Would a senior RN engineer approve this?
- **All network I/O goes through `apiRequest` (`src/api/client.ts`).** No raw `fetch` in components, screens, or hooks. The 401-refresh flow, timeout, and error normalisation only work if everything funnels through this one entry point.
- **Tokens only live in `expo-secure-store`, only read through `src/auth/tokenStorage.ts`.** Never touch SecureStore directly from a component, and never put tokens in `AsyncStorage`, Redux, React state, or a context value.
- **Decoded JWT claims are a UI hint, not a security boundary.** `src/auth/jwt.ts` reads the access-token payload client-side for things like role-based screen routing. A tampered token still decodes — the backend re-checks every request, and so must you for anything that matters.
- **Components stay presentational.** Side effects (network, storage, navigation triggers, timers) live in hooks, contexts, or `src/api/`. A screen file should mostly be JSX + a few hook calls.
- **No browser globals.** TypeScript's DOM lib loads by default and silently lets `DOMException`, `localStorage`, `window`, `document`, `XMLHttpRequest`, `Blob`, etc. typecheck. None of them exist in Hermes — referencing them is a runtime `ReferenceError`. Use `err instanceof Error && err.name === 'AbortError'`, `expo-secure-store`, `expo-file-system`, etc.

## Bug Fixing Rules

- Reproduce first. If you can't reproduce it, you can't fix it — say so and ask.
- **When the app breaks right after your change, suspect your change before the environment.** Especially structural changes to Expo Router route files — a deleted/renamed route (e.g. a tab group losing its `index.tsx`) hangs the splash screen with no error. A "stale Metro cache" theory once cost a full round-trip when the real cause was exactly this. Environment checks (LAN IP, backend, Metro) come second — run the `/device-verify` preflight for those.
- Read the actual error: stack trace, Metro logs, device console. For network bugs, check `ApiError.status` (transport failures use `NETWORK_ERROR_STATUS = 0`) and `ApiError.payload` before guessing.
- Trace to root cause. Don't paper over symptoms with a `try/catch` that swallows.
- Only ask clarifying questions when the cause is genuinely undetermined after looking.

## Task Management Rules

- Write a plan to `tasks/todo.md` before any non-trivial implementation. Mark items done as you go.
- After a correction from the user, append the lesson to `tasks/lessons.md` (create it if missing). Re-read it at the start of every session.
- Never start a new task without updating the task file.

## Verification Rules

- Pure-logic changes (api client, auth, jwt, utils): `npx tsc --noEmit` + `npm test` must pass before reporting done.
- UI changes: typecheck + tests, **and** actually run the app on the iOS simulator (or device via Expo Go) and confirm the change renders + behaves as intended. Screenshot when useful. UI work is not "done" because tests pass — there aren't UI tests yet (see Testing policy). Use the `/device-verify` skill: preflight (LAN IP vs `.env.local`, backend health, Metro) before the checklist, and seed data via `/seed-demo-data`, never ad-hoc SQL.
- **Route files are read once at startup.** Adding/renaming/deleting anything under `app/` needs a full `expo start` restart — Fast Refresh will keep serving the old route tree and mislead you.
- Never mark a task complete without proving it works.

## Commit Rules

- Stage only files directly required by the change: source, tests, types, `app.json`/`package.json`/`package-lock.json` when intentional.
- Do not commit planning artefacts (`tasks/todo.md`, scratch notes), `.env.local`, or anything under `.expo/`.

---

## What this project is

The React Native (Expo) mobile client for **The FMCG Hub** supply-chain tracker. iOS + Android. Four user roles (Admin, Morocco logistics agent, UK clearing/delivery agent, Customer) consume the same FastAPI backend at `https://api.thefmcghub.com` and read/write the trading workflow (PO → Booking → Container → Delivery → Customer Payment).

Bundle / package: `com.thefmcghub.logistics` (permanent — do not change).

---

## Stack

| Layer                | Technology                                                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Framework            | Expo SDK 54 (pinned — see Expo SDK pin note below)                                                                                                      |
| Runtime              | React Native 0.81, React 19.1, Hermes                                                                                                                   |
| Language             | TypeScript ~5.9 (strict; no DOM lib used)                                                                                                               |
| Auth storage         | `expo-secure-store`                                                                                                                                     |
| JWT decode (UI only) | `jwt-decode`                                                                                                                                            |
| HTTP                 | native `fetch`, wrapped by `src/api/client.ts`                                                                                                          |
| Tests                | jest 29 + ts-jest (node env, pure-logic only)                                                                                                           |
| Navigation           | Expo Router (file-based; routes under `app/`, route groups `(auth)` + `(authed)`; the signed-in area is a bottom-tab navigator under `(authed)/(tabs)`) |
| Server state         | TanStack Query — `QueryClientProvider` in `app/_layout.tsx`; hooks in `src/api/queries/`                                                                |
| Client state         | React Context only (`AuthContext`). No Redux/Zustand until there's a concrete need                                                                      |
| Env loading          | `expo` reads `.env`, `.env.local`, `.env.production` at bundler start                                                                                   |

---

## Architecture invariants

- **One HTTP client.** `apiRequest<T>(path, options)` in `src/api/client.ts` is the only function that calls `fetch`. It owns: base-URL prefixing, JSON content negotiation, bearer-token injection, 15 s default timeout, uniform `ApiError`, and the 401→refresh→retry-once flow.
- **Auth-endpoint calls opt out.** Login and refresh itself pass `auth: 'skip'` to `apiRequest` — a 401 there means bad creds / dead refresh token and must propagate, not trigger another refresh.
- **Single-flight refresh.** N concurrent 401s run exactly one `POST /api/v1/auth/refresh`. Don't add a parallel path.
- **Session-expired is an event, not a return value.** On refresh failure, `client.ts` calls `clearTokens()` and `emitSessionExpired()` (`src/auth/sessionEvents.ts`). `AuthProvider` listens and flips status → `anonymous`, which re-renders the login screen. Don't try to navigate from inside the API client.
- **`AuthContext` is the only consumer of token storage.** Screens read `useAuth()` for `{ status, user, signIn, signOut }` — they don't call `getAccessToken()` themselves.
- **Theme tokens, not inline styles.** Colours, spacing, radii, shadows, and the Geist type scale live in `src/theme/tokens.ts` and are consumed via `src/theme/index.ts`. Hard-coded hex/px or a raw `fontWeight` in a component is a code-smell. See **Theme & design system** below for the full vocabulary.
- **Shared UI primitives in `src/components/ui/`.** `Button`, `Card`, `EmptyState`, `FormError`, `IconBox`, `Input`, `ListItem`, `Pill`, `ScreenContainer`, `Select`, `Spinner`, `StatusPill`, `Text`, plus the `ToastProvider`/`useToast` feedback system and the `animateLayout()` helper (call before a collapsible's `setState` toggle). Reach for these before building bespoke views. Empty lists render `<EmptyState icon? title subtitle?>`, not a hand-rolled centered `<Text>`; the 36×36 icon squares are `<IconBox>`.
- **One status-pill component.** Any badge that renders a `BookingStatus` or `ContainerLifecycleStatus` goes through `<StatusPill>` (`src/components/ui/StatusPill.tsx`). It maps each enum value to a tone via an exhaustive `Record<...>` — a new backend enum value will fail TS until the mapping in `statusPillMapping.ts` is updated. Don't render raw status strings, and don't reimplement a local tone-picker.

---

## Theme & design system

Phase 9 ported the client prototype's visual identity onto the tokens: a warm
"paper" palette, the **Geist** typeface, and soft/ink semantic color pairs. It
was a **reskin only** — no IA/feature/backend changes; the prototype's bigger
ideas (4-tab IA, Money-risk dashboard, enriched Inbox, Admin console) are
catalogued in `mobile-redesign-roadmap.md` as later phases. Everything funnels
through `src/theme/tokens.ts` + the primitives in `src/components/ui/`, so a
screen almost never sets a color/font itself.

### Palette (soft/ink convention)

`colors` is a warm-paper surface ramp (`bg`/`bgSoft`/`bgSunk`/`bgElev`), a cool
ink text ramp (`ink`/`ink2`/`ink3`/`ink4`), borders (`line`/`lineStrong`), the
brand navy (`primary`/`primarySoft`/`primaryInk`), and four semantic triplets —
`green`/`amber`/`red`/`info`, each with a `*Soft` (surface fill) and `*Ink`
(text-on-fill) variant. **A pill or banner uses `xSoft` as fill + `xInk` as
text** (low-saturation surface, high-contrast text), not a saturated outline.

The pre-Phase-9 export names are kept as **aliases** pointing at the new palette
(`text→ink`, `textMuted→ink3`, `border→line`, `surface→bgSoft`,
`primaryText→primaryInk`, `error→red`, `errorSurface→redSoft`, `warning→amber`,
`success→green`) so screens importing `colors.text` etc. didn't churn. Prefer
the new names in new code.

### Typography — Geist (weight-by-family)

**Custom RN fonts do NOT synthesize weight.** `fontFamily:'Geist'` +
`fontWeight:'700'` renders Regular, not Bold. So every cut is loaded as its own
family in `app/_layout.tsx`: `Geist-Regular/Medium/SemiBold/Bold` +
`GeistMono-Regular/Medium` (from `@expo-google-fonts/geist` + `geist-mono`). The
**only** place that maps a `(weight, mono)` pair to a family string is
`fontFamily()` in `tokens.ts`; the `<Text>` primitive is its sole caller.

- **Never set `fontWeight` in a component.** Use `<Text weight="semibold">` (or
  a variant whose default weight is heavier). The weight prop picks the family.
- **`<Text>` is the font funnel** — apply Geist there, not per screen. Variants:
  `display`/`heading`/`title`/`body`/`label`/`small`/`overline` (the tracked
  uppercase label, e.g. "BOOKINGS"). Each carries a default weight; override via
  `weight`.
- **`mono` is for refs/IDs/amounts** — container/booking refs, vessel IMO,
  invoice numbers, the state-machine chip text, monetary figures in dense rows.
  `<Text mono>`. Geist Mono ships Regular + Medium only (heavier cuts fall back
  to Medium).

### Sizes, overlays (Phase 11)

`sizes` holds fixed non-spacing dimensions — `trackThin 6` (ProgressBar),
`trackMicro 4` (stepper/card progress segments), `dotSm 8` (status dots),
`iconBox 36` (IconBox), `touchTarget 44` (min row height). `overlays` holds the
translucent scrims (`dim` for sheet backdrops, `ripple` for `android_ripple`).
A raw `height: 6` / `rgba(...)` in a component is the same code-smell as a raw
hex. `ink4` was darkened to `#8a8f94` in Phase 11 (3.1:1 on `bg` — the WCAG
large-text floor; a true 4.5:1 would land darker than `ink3` and invert the
ramp). Chevrons/carets are Ionicons (`chevron-forward/down/up`, usually 18
`ink4`), never the text glyphs `›`/`▾`/`⌄`.

### Type scaling

The `<Text>` primitive (and `Input`'s `TextInput`) sets
`maxFontSizeMultiplier={1.3}` so the OS accessibility font setting scales text
without exploding dense rows. Don't override it per-screen.

### Radii, shadows

`radii` = `sm 6 / md 10 / lg 14 / xl 20 / pill 999`. `shadows` = `sh1` (hairline)
/ `sh2` (resting card) / `sh3` (raised) / `sheet` (bottom sheets, casts upward) —
RN-friendly maps (iOS `shadow*` + Android `elevation`); spread `...shadows.sh2`.
RN can't draw the prototype's 1px ring via shadow, so `Card` pairs `sh2` with a
real `borderWidth:1` + `line`.

### Font-loading boot sequence (`app/_layout.tsx`)

`SplashScreen.preventAutoHideAsync()` runs at module load. `RootLayout` loads
the six families via `useFonts`, **returns `null` until they resolve** (so the
first painted frame is already in-font — no system-font flash), then hides the
splash in an effect once `fontsLoaded || fontError`. On font error it falls back
to the system font rather than hanging on the splash. The splash background is
the brand paper `#fcfaf6` (`expo-splash-screen` plugin in `app.json`).

### Primitives

All restyled to the prototype: `Pill` (soft/ink, full pill radius, borderless),
`Button` (navy primary + `sh2`, secondary/ghost), `Card` (elevated white + ring

- `sh2`), `Input`/`Select`/`DateField` (elevated field, navy focus ring),
  `FormError` (`redSoft`/`redInk`), `ProgressBar` (rounded navy fill on `bgSunk`),
  `BookingStepper` (presentational segmented DRAFT→…→DONE bar fed by
  `BookingStatus`), plus `Toast`/`Spinner`/`ScreenContainer`/`ListItem`. Restyle a
  primitive, not 40 screens. Don't change a primitive's props/behavior — visual
  only.

---

## Folder map

| Folder                  | What lives here                                                                                                                                                                                                                                                            | Example                                                                                                                                                                               |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/`                  | Expo Router routes. Route groups `(auth)` (anon-only) + `(authed)` (signed-in); the signed-in area is the 4-tab group `(authed)/(tabs)` (Bookings / Alerts=Money-risk / Inbox=notifications / Admin — role-aware). Each folder has a `_layout.tsx` for its guard/navigator | `app/(authed)/(tabs)/bookings/[id]/index.tsx`                                                                                                                                         |
| `src/api/`              | HTTP client + typed endpoint wrappers + React-hook-shaped queries                                                                                                                                                                                                          | `client.ts`, `authedClient.ts`, `queries/useBookings.ts`, `queries/useBooking.ts`                                                                                                     |
| `src/api/queries/`      | TanStack Query read hooks                                                                                                                                                                                                                                                  | `useBookings.ts`, `useBooking.ts`, `useContainer.ts`, `useMoneyRisk.ts`, `useBrokers.ts`, `useCompanies.ts`, `usePortTemplates.ts`, `useUsers.ts`, `useInvites.ts`, `useAuditLogs.ts` |
| `src/api/mutations/`    | TanStack Query write hooks (invalidate-and-refetch)                                                                                                                                                                                                                        | `useUpdatePortStatus.ts`, `useCreateCustomerPayment.ts`, `useUploadDocument.ts`, `useCreateBroker.ts`, `useCreateCompany.ts`, `useUpsertPortTemplate.ts`, `useSendInvite.ts`          |
| `src/api/documents/`    | Imperative (non-cached) document helpers                                                                                                                                                                                                                                   | `getDownloadUrl.ts`                                                                                                                                                                   |
| `src/api/types/`        | Hand-typed TS mirrors of backend Pydantic schemas. Split per domain                                                                                                                                                                                                        | `booking.ts`, `container.ts`, `enums.ts`, `admin.ts`                                                                                                                                  |
| `src/auth/`             | Auth state machine, token storage, JWT decode, session events, role gating                                                                                                                                                                                                 | `AuthContext.tsx`, `tokenStorage.ts`, `jwt.ts`, `sessionEvents.ts`, `authApi.ts`, `permissions.ts`                                                                                    |
| `src/components/`       | Cross-cutting components that compose primitives                                                                                                                                                                                                                           | `AppHeader.tsx`, `documents/DocumentsList.tsx`                                                                                                                                        |
| `src/components/ui/`    | Reusable presentational primitives — no network, no storage                                                                                                                                                                                                                | `Button.tsx`, `Card.tsx`, `StatusPill.tsx`, `ScreenContainer.tsx`                                                                                                                     |
| `src/config/`           | Env-derived constants. Single export per concern                                                                                                                                                                                                                           | `api.ts` (`API_BASE_URL`)                                                                                                                                                             |
| `src/theme/`            | Design tokens + theme helpers                                                                                                                                                                                                                                              | `tokens.ts`, `index.ts`                                                                                                                                                               |
| `src/lib/`              | Framework-agnostic pure helpers (no React, no network)                                                                                                                                                                                                                     | `money.ts`, `idempotency.ts`, `relativeTime.ts`, `auditFormat.ts`                                                                                                                     |
| `src/forms/`            | zod schemas + form→body mappers for non-trivial forms                                                                                                                                                                                                                      | `customerPaymentSchema.ts`, `brokerSchema.ts`, `companySchema.ts`, `portTemplateSchema.ts`, `inviteSchema.ts`                                                                         |
| `src/notifications/`    | Expo push registration helper + the runtime tap/foreground listener component (`NotificationDeepLinker`)                                                                                                                                                                   | `pushRegistration.ts`, `NotificationDeepLinker.tsx`                                                                                                                                   |
| `src/__mocks__/`        | Jest manual mocks for native modules that don't run in node                                                                                                                                                                                                                | `expo-secure-store.ts`, `expo-crypto.ts`, `expo-notifications.ts`, `expo-device.ts`                                                                                                   |
| _(future)_ `src/hooks/` | Cross-screen hooks that aren't tied to a single domain                                                                                                                                                                                                                     | —                                                                                                                                                                                     |

Tests sit next to the file under test (`client.test.ts` next to `client.ts`), not in a parallel tree.

Feature-scoped areas under `src/features/<domain>/`: `dashboard/` (role→greeting/sections selector), `alerts/` (notification label/tone map), and `moneyRisk/` (Money-risk cards + `MoneyHeroCards` + the pure `moneyRiskFormat` helpers). Feature-scoped UI + pure helpers that aren't a reusable primitive live here.

---

## Navigation (4 role-aware tabs + nested Bookings stack)

The signed-in area is a **bottom-tab navigator** with **four** destinations (Phase 10 IA). **The tab labels are counterintuitive — read this carefully:**

| Tab                    | File                    | Shows                                                                                          | Roles           |
| ---------------------- | ----------------------- | ---------------------------------------------------------------------------------------------- | --------------- |
| **Bookings** (landing) | `(tabs)/bookings/`      | The bookings list **+** the merged "Today" dashboard header (role greeting + money hero cards) | all             |
| **Alerts**             | `(tabs)/money-risk.tsx` | The **Money-risk** dashboard (A/R aging · demurrage · disputes) — **NOT notifications**        | admin, uk_agent |
| **Inbox**              | `(tabs)/inbox.tsx`      | The **notifications** feed (the unread badge lives here now)                                   | all             |
| **Admin**              | `(tabs)/admin/`         | The admin console — a stack. PEOPLE + OPERATIONS + SYSTEM all live (Phase 13a/13b)             | admin           |

⚠️ **Alerts = Money-risk; Inbox = notifications.** This is backwards from intuition: the notifications feed moved off the old "Alerts" tab, and "Alerts" was repurposed to the Money-risk dashboard.

```
app/(authed)/_layout.tsx              # auth guard → Stack (headerShown:false); renders (tabs)
app/(authed)/(tabs)/_layout.tsx       # <Tabs>: Bookings | Alerts(money-risk) | Inbox(+badge) | Admin
app/(authed)/(tabs)/money-risk.tsx    # "Alerts" tab — Money-risk dashboard (see Money-risk)
app/(authed)/(tabs)/inbox.tsx         # "Inbox" tab — notifications feed (see Notifications)
app/(authed)/(tabs)/admin/_layout.tsx # "Admin" tab — <Stack>; registers the create/edit modals
app/(authed)/(tabs)/admin/index.tsx   # admin section menu (PEOPLE/OPERATIONS/SYSTEM)
app/(authed)/(tabs)/admin/users|invites/   # People — users list, invites list + send-invite modal
app/(authed)/(tabs)/admin/audit-log|system/ # System — audit-log feed, static push/security panels
app/(authed)/(tabs)/admin/**          # port-templates / brokers / end-customers (Operations)
app/(authed)/(tabs)/bookings/_layout.tsx   # <Stack> for the Bookings tab; registers the modals
app/(authed)/(tabs)/bookings/index.tsx     # landing: dashboard header + hero cards + bookings list
app/(authed)/(tabs)/bookings/**            # list → [id] detail → containers/[cid] → modals
```

- **Role-aware tabs (cosmetic gate; server enforces too).** Money-risk is hidden for non-admin/uk_agent and Admin for non-admin via `href: null` in `_layout.tsx` (keyed off `useAuth().user?.role`). The Money-risk **query** is additionally `enabled`-gated (`canSeeMoneyRisk(role)` in `useMoneyRisk`) so a hidden-tab role never fires the doomed 403 — same pattern as supplier-payments. So: admin sees all 4 tabs, uk_agent sees 3 (no Admin), morocco_agent/customer see 2 (Bookings + Inbox).
- **Cold start lands on Bookings.** The tab group needs a screen for its base path, so `(tabs)/index.tsx` is a hidden (`href: null`) redirect → `<Redirect href="/bookings" />`. (The old standalone Dashboard that used to live at `index.tsx` was merged into the Bookings-tab landing.) **Don't remove the index route** — a tab group with no base-path screen fails route resolution at startup, which surfaces as a frozen splash (the root only hides the splash in a post-commit effect).
- **The unread badge is on Inbox** (moved from the old Alerts tab). `useUnreadCount` still derives it from `GET …?unread_only=true&limit=1` → `.total`.
- **Where new screens go.** A new _top-level destination_ is a tab (a file/dir under `(tabs)` + a `<Tabs.Screen>`). A new _bookings detail/form screen_ goes inside the Bookings-tab stack (`(tabs)/bookings/…`) so it pushes within that tab.
- **Modals live in the Bookings-tab stack.** `presentation: 'modal'` for port-status / dispute / record-payment is declared in `(authed)/(tabs)/bookings/_layout.tsx` (names relative to it, e.g. `[id]/containers/[cid]/port-status`) — **not** in `(authed)/_layout.tsx`.
- **Route groups are invisible in the URL.** `(authed)` and `(tabs)` are parenthesised groups, so a booking's URL stays `/bookings/{id}` regardless of nesting. Switch tabs with a plain href (`router.push('/money-risk')`, `router.push('/inbox')`).
- **Push deep-link fallback is `/inbox`.** A push with a `booking_id` opens `/bookings/{id}`; one without falls back to `/inbox` (the notifications feed) — see Notifications.

### Path alias `@/`

`tsconfig.json` maps `@/* → ./*`. **`app/` files use the `@/` alias** (`@/src/...`) — verified to resolve under both `npx tsc --noEmit` and a real `npx expo export` bundle on SDK 54 (Expo's Metro reads tsconfig `paths`; there is no `baseUrl` — that was the Phase 1 footgun). **`src/` files keep relative imports**, because `jest.config.js` has no `@/` moduleNameMapper and the existing tests mock relative paths; keeping `src/` relative means no jest change is needed. (`@expo/vector-icons` is an explicit dependency so tsc can resolve its types — it was previously only transitively present under `expo/node_modules`, which Metro resolves but tsc does not.)

## Bookings landing (merged dashboard)

There is no standalone Dashboard tab anymore (Phase 10). The Bookings-tab list screen (`(tabs)/bookings/index.tsx`) carries a **dashboard header** above the list:

- **Role greeting** — `dashboardConfig(role).greeting` (`src/features/dashboard/dashboardSections.ts`, pure + tested). The role label only; there is no `/me` endpoint and the JWT carries no name.
- **Money hero cards (admin/uk_agent only)** — two cards, aged A/R exposure (£) + soonest demurrage countdown, sourced from the same `useMoneyRisk` query the Money-risk screen uses (one shared `['money-risk']` cache slot, not a second fetch). Tapping either navigates to the Alerts (Money-risk) tab. Hidden + query-gated for other roles.
- **Status-count strip (customer / morocco_agent)** — roles without the money cards get a one-line "2 in transit · 1 complete" strip instead, derived client-side from the same list page via `countByStatus`/`formatStatusCounts` (`src/features/bookings/bookingStatusCounts.ts`, pure + tested). No extra fetch.
- The live bookings list follows (one `useBookings({ limit: 200 })` page) rendered as rich `<BookingCard>`s (`src/features/bookings/BookingCard.tsx`): mono ref + `StatusPill`, route/ETA, goods, counts·vessel lines from the **optional** list summary fields (`po_count`, `container_count`, `vessel_name`, `eta`, `port_of_discharge`, `product_summary` on the `Booking` type — typed optional so the app works against a backend without the enrichment), plus a segmented progress bar. The status→step mapping is the pure `bookingProgress.ts` (`BOOKING_STAGES`/`bookingStageIndex`, tested) shared with `BookingStepper` — never fork it.
- **Deferred (→ roadmap):** the prototype's "N things need you today" action banner and the All / Active / Needs-me / Mine filter chips (cross-booking "needs me" feature work). The Phase-5 status-count grid was retired here in favour of the live list — faceted counts return with the filter chips.

## Money-risk (the "Alerts" tab)

`(tabs)/money-risk.tsx` consumes `useMoneyRisk` (`src/api/queries/useMoneyRisk.ts`, key `['money-risk']`) → `GET /api/v1/money-risk` → `MoneyRiskOut { ar_aging, demurrage, disputes }`. Gated to **admin + uk_agent** (the backend `require_role`); `canSeeMoneyRisk(role)` drives both the tab `href` and the query `enabled`.

- **Money fields are strings.** The route uses `response_model`, so every `Decimal` serialises to a JSON **string**. Types in `src/api/types/moneyRisk.ts`; format/sum via `src/lib/money.ts` (`formatMoney`/`sumDecimalStrings`) — never `parseFloat`.
- **Demurrage is whole days.** The backend `Vessel.ata` is a date (no time), so `days_remaining` is an int (negative = expired). The prototype's "2d 14h" is design flavour — `formatDaysRemaining` renders "Nd"/"Today"/"Expired", no fabricated hours.
- **Outstanding £ is full exposure**, not netted against banked tranches; aging clock is `Container.updated_at` (approximate — no precise `delivered_at` yet). These are deliberate backend approximations.
- Cards (`src/features/moneyRisk/`): `ARAgingCard` (total + buckets + tap-to-expand drill-in over the inline `containers` array), `DemurrageCard` (countdown rows), `DisputesCard` (health line + a tap-through row per **unacknowledged** dispute → `/bookings/{booking_id}`, where the dispute is acknowledged). The disputes section carries `items: DisputedContainer[]` (each with `booking_id`) — the deep-link target, since the ack action lives on the container detail screen, not here. `MoneyHeroCards` is the compact Bookings-landing summary. Pure helpers in `moneyRiskFormat.ts` (tested).

## Notifications (Inbox feed)

Endpoints (`parcel-track/app/api/routes/notifications.py`):

- `GET /api/v1/notifications?unread_only=&limit=&offset=` → `PaginatedResponse<NotificationOut>` (`useNotifications`, key `['notifications', filters]`).
- **`PATCH`** `/api/v1/notifications/{id}/read` (no body) → `{ message }` (`useMarkNotificationRead`). It is PATCH, **not** POST.
- There is **no** `/unread-count` and **no** mark-all-read endpoint. The tab badge derives the count from `GET …?unread_only=true&limit=1` → `.total` (`useUnreadCount`, key `['notifications', 'unread-count']`).
- **Prefix invalidation:** `useMarkNotificationRead` invalidates the bare `['notifications']` prefix — one call refetches every list query _and_ the unread-count badge (both sit under that prefix).
- **`NotificationOut`** = `{ id, type, title, message, read, booking_id, created_at }` — the field is `message` (not `body`), and the only entity reference is `booking_id` (nullable). So a row **deep-links to `/bookings/{booking_id}` when set**, and is mark-read-only otherwise (no `entity_type`/`entity_id` exist).
- **`NotificationType`** has 15 values (mirror in `src/api/types/enums.ts`); `NOTIFICATION_LABELS`/`NOTIFICATION_TONES` (`src/features/alerts/notificationDisplay.ts`) map each exhaustively — a new backend value fails the typecheck until added.

### Push notifications (OS-level delivery)

The in-app Inbox list is one channel; **Expo Push** is the other. Phase 8 wired the client. The backend already does its half — `User.expo_push_token` column + `PATCH /api/v1/notifications/push-token?token=<expo_push_token>` (token is a **query param**, not a body) + `NotificationService.send` enqueues a Celery `send_push_notification` task that POSTs to Expo with `{ to, title, body, sound, data: { notification_id, type, booking_id? } }`. Re-registering overwrites — last write wins — so single-device-per-user is a documented limitation, not a bug.

- **Where it lives.** `src/notifications/pushRegistration.ts` (helpers: `registerAndSyncPushToken`, `sendTokenToServer`, `buildPushTokenPath`, `setupAndroidChannel`) + `src/notifications/NotificationDeepLinker.tsx` (the listener component mounted inside `<AuthProvider>`). Module-load-time `Notifications.setNotificationHandler(...)` is in `app/_layout.tsx`.
- **When the token registers.** Fire-and-forget after each successful `signIn` and on every cold-start while authenticated (`AuthProvider`). Guarded by a module-scope flag so it runs at most once per process. Errors are swallowed — push registration must NEVER block sign-in UX or crash on permission denial. Sign-out does **not** clear the token server-side (no DELETE route, and a re-login would just rewrite it).
- **Permission UX.** OS prompt shown once at first sign-in via `requestPermissionsAsync`. On denial, no nag, no in-app banner — the Inbox tab is the fallback. Users can re-enable in OS settings later.
- **Foreground handler.** `setNotificationHandler` returns `{ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false }` (SDK 54 keys — the old `shouldShowAlert` is deprecated). The received-listener invalidates `['notifications']` so the Inbox list + unread badge bump in ~1s, same prefix-invalidation trick `useMarkNotificationRead` uses.
- **Tap → deep-link.** The response listener reads `notification.request.content.data` (the Celery task ships `{ notification_id, type, booking_id? }` — see `parcel-track/app/background/tasks.py` `send_push_notification`). If `booking_id` is present → `router.push('/bookings/{id}')`, else → `/inbox` (the notifications feed moved to the Inbox tab in Phase 10). Also fires mark-read via `authedApiRequest` PATCH (we're outside React render, so we can't use the mutation hook). Cold-launch-from-tap: `getLastNotificationResponseAsync()` once on mount — the live listener does NOT fire for the launch event itself.
- **Hard rule.** Token register + mark-read MUST go through `authedApiRequest`, not raw `fetch` — else the 401-refresh flow doesn't apply.
- **`projectId`.** Read from `Constants.expoConfig?.extra?.eas?.projectId` (`expo-constants`). Pre-EAS / Expo Go works fine with `undefined`. After `eas init` it's mandatory for production builds — the helper threads it through whenever set. Never hardcode.
- **Android channel.** `setupAndroidChannel` creates a single `'default'` channel at `AndroidImportance.MAX` on first call — Android won't render banners otherwise.
- **Tests.** `pushRegistration.test.ts` asserts the URL shape + happy path + error-swallow + idempotence. Mocks: `src/__mocks__/expo-notifications.ts`, `expo-device.ts`, `expo-constants.ts`, `react-native.ts` (all under jest's `moduleNameMapper` in `jest.config.js`). No UI tests for `NotificationDeepLinker` — covered by device verification.
- **Production credentials.** Standalone iOS/Android builds need APNs key + FCM v1 service-account JSON uploaded via `eas credentials`. Owned by the EAS phase, not this one. Expo Go uses Expo's hosted push service and works without those creds.

---

## Admin console (the "Admin" tab)

Phase 13a turned the Admin tab from a single "coming soon" shell into a **stack** (mirrors the Bookings tab): `(tabs)/admin/_layout.tsx` (Stack — registers the create/edit modals), `admin/index.tsx` (the section menu), and the OPERATIONS screens. Phase 13b filled in **PEOPLE** (Users, Invites) and **SYSTEM** (Audit log, Push, Security). The tab stays `name="admin"` in `(tabs)/_layout.tsx`, so the existing `href: null` admin-only gating is unchanged. Every section-menu row now navigates (no more "Soon" rows); every sub-screen re-checks `canManageAdmin` and renders a "Not permitted" body for a deep-linked non-admin.

### People + System (Phase 13b — view + send-invites)

Backed by the admin read endpoints in `parcel-track/app/api/routes/admin.py` (all `require_admin`, read-only) plus the existing `POST /auth/invite` for sends. **Scope is view + send-invites only** — no revoke/deactivate/role-change (no backend mutation for those this round). Types in `src/api/types/admin.ts` (`UserAdmin`, `Invite`, `AuditLogEntry`, `InviteCreate`); role labels/order in `enums.ts` (`USER_ROLES` + `USER_ROLE_LABELS`).

- **Users** — `useUsers` (key `['users', filters]`, `GET /api/v1/users` → `PaginatedResponse<UserAdmin>`, gated `enabled: isAdmin`). The list reuses the backend `UserOut` shape (no separate UserAdminOut). The screen fetches one capped page (`limit: 200` — the user base is tiny) and computes the "N active · X admin · Y agent · Z customer" summary client-side. Role renders via **`Pill`** (neutral tone), **not** `StatusPill` (roles aren't booking/lifecycle enums). Read-only.
- **Invites** — `useInvites` (key `['invites', { status, … }]`, `GET /api/v1/invites?status=pending`, gated). Lists pending invites (email · role chip · "expires in N days"). `token_hash` is never serialised by the backend. "Send invite" opens the `invites/new` modal → `useSendInvite` (`POST /api/v1/auth/invite` — note the `/auth` prefix, **not** the bare `/invite` the plan assumed; the read list is `/invites` with no prefix). `inviteSchema` (`src/forms/`) validates email + a role Select (refine-not-enum so the blank default validates). Success → toast + `router.back()`; the mutation invalidates the `['invites']` prefix. **NO Idempotency-Key** (not a financial create) — the mutation test asserts no `headers`.
- **Audit log** — `useAuditLogs` (key `['audit-logs', { limit, offset }]`, `GET /api/v1/audit-logs`, newest first, gated). Global feed with **load-more** (grows `limit`; the hook sets `placeholderData: keepPreviousData` so a bigger window doesn't flash the spinner). Each row: `entity_type` chip, humanized `action` (`humanizeAction` in `src/lib/auditFormat.ts`, e.g. `booking.status_changed` → "Booking status changed"), actor name, relative time; tap to expand the `old_value`→`new_value` snapshot + IP. **`old_value`/`new_value` are JSON strings or null** — `prettyJson` (same file) pretty-prints them **defensively** (guards null / non-JSON). Read-only — the audit table is append-only.
- **Push notifications + Security = static info panels** (`admin/system/push.tsx`, `security.tsx`). **No fetch, no config.** Push lists the 15 `NotificationType` values + labels, reusing `NOTIFICATION_LABELS` from `src/features/alerts/notificationDisplay.ts` (don't retype them); Security is a static "JWT · Redis revocation · bcrypt" card.

### Operations (Phase 13a)

- **Three resources, all on existing admin-gated APIs (mobile-only phase).** Backend: `app/api/routes/parties.py` (`/brokers`, `/companies`) + `port_templates.py` (`/port-templates`). **List (GET) is open to any authenticated user; create/upsert is `require_admin`.** Every list query is still gated `enabled: isAdmin` (via `canManageAdmin` in `permissions.ts`) so a deep-linked non-admin never fires a request, and each screen renders a "Not permitted" body (defense-in-depth; the server is the real gate).
  - **Brokers** — `useBrokers` (key `['brokers', filters]`) + `useCreateBroker` (invalidate `['brokers']`). Fields `{ code, name, phone? }`. List + create only (no PATCH/DELETE on the backend — no edit/delete screens).
  - **End customers (companies)** — `useCompanies` (key `['companies', filters]`) + `useCreateCompany` (invalidate `['companies']`). Fields `{ legal_name, aliases?[], registration_no?, vat_no?, default_address? }`. **`aliases` is a `string[]`** — the form collects a comma-separated text field and `companySchema`'s `toCreateBody` splits/trims/drops-blanks into the array. List + create only.
  - **Port templates** — `usePortTemplates` (key `['port-templates']`, a **plain non-paginated list**, one row per saved UK port) + `useUpsertPortTemplate` (variables `{ port, body }`, `PUT /port-templates/{port}`, invalidate `['port-templates']`). **Edit/upsert-only**: the six UK ports are a fixed enum (`UKPort`), so the list renders _every_ port (defaults / "Not set" for unsaved ones) and the form upserts — there's no "create a port".
- **`UKPort` lives in `src/api/types/enums.ts`** (`UK_PORTS` ordered array + exhaustive `UK_PORT_LABELS`). Admin types are in `src/api/types/admin.ts`.
- **Money discipline.** Port-template rate fields (`detention_rate_gbp_after` / `demurrage_rate_gbp_after`) are backend `Decimal` → JSON **strings**; kept `string` end-to-end, displayed via `formatMoney`, never `parseFloat`. Free-days are plain ints. `portTemplateSchema`'s `toUpsertBody` converts free-days to `number` but passes rates through as strings.
- **NO `Idempotency-Key` on any of these endpoints.** That header is only for the three financial creates (customer/supplier payment, invoice). The broker/company/port-template mutation tests assert the request carries **no** `headers`. Don't add one.
- **Forms** in `src/forms/`: `brokerSchema.ts`, `companySchema.ts`, `portTemplateSchema.ts` (react-hook-form + zod; the broker form uses a schema for uniformity even at 3 fields). All on Phase-9 primitives + `KeyboardAvoidingView`; success toast + `router.back()`, inline `<FormError>` on error (toasts don't paint over modals).

---

## API client error contract

Every call through `apiRequest` either resolves with the parsed JSON body (typed via the caller's `<T>`) or throws an `ApiError`. There is no third shape.

```ts
class ApiError extends Error {
  readonly status: number; // HTTP status, or 0 for transport-level failure
  readonly payload: unknown; // parsed response body (or original error for status === 0)
  readonly isNetworkError: boolean; // true iff status === 0
}
```

- `status === 0` → DNS, TLS, offline, or our own 15 s timeout. Show "check your connection," offer retry. Never log the user out on this.
- `status === 401` → only seen at the call site if `auth: 'skip'` or if the post-refresh retry also 401'd. A `'normal'` call that fires session-expired throws a 401 too; `AuthProvider` handles the UX, you just need to bail.
- `status === 422` → Pydantic validation error. `client.ts` already extracts a readable message via `extractErrorMessage` — surface `err.message` to the user directly.
- Other 4xx/5xx → `err.message` is the backend `detail` string when present, else `Request failed: <status>`.

Do not branch on `err.payload` shapes in screens — if you need structured access to validation errors, add a helper to `src/api/` rather than spreading the knowledge of FastAPI's response envelope.

---

## Auth flow (401 → refresh → retry)

1. Authenticated request fires through `apiRequest` (`auth: 'normal'`, default).
2. On 401, `refreshAccessToken()` runs (single-flighted across concurrent callers) — `POST /api/v1/auth/refresh` with the stored refresh token.
3. On refresh **success**: new pair persisted via `setTokens()`, original request retried **once** with the new access token. A second 401 surfaces as a 401 — we never loop.
4. On refresh **failure** (any non-2xx, network error, missing refresh token): `clearTokens()` + `emitSessionExpired()`. `AuthProvider` flips to `anonymous`; UI re-renders to the login screen.

Auth-endpoint calls (`/auth/login`, `/auth/refresh`) **must** pass `auth: 'skip'`. A 401 on those is a real auth failure and must propagate as-is.

### Cached user identity

`useAuth()` exposes `user: { id, role } | null`, derived by decoding the access token payload (`src/auth/jwt.ts`, `jwt-decode`). **This is a UI hint, not authorisation.** Signature verification is the backend's job — the client only reads claims to decide which tabs/screens to show. Anything sensitive must be enforced server-side and the client must handle the 403 gracefully.

When the backend grows a `/me` endpoint (see Deferred fixes), swap `decodeUserFromToken` for a real fetch and extend `User` with `name` + `email`. Cold-start can become a real `/me` call then too — currently we lazily trust the stored token and let the first authenticated request self-heal via the 401 flow.

---

## Server state (TanStack Query)

All server data flows through TanStack Query. `QueryClientProvider` is wired in `app/_layout.tsx` with `staleTime: 30s`, `retry: 1`, `refetchOnWindowFocus: true`. Every query hook lives in `src/api/queries/` and calls `authedApiRequest<T>(path)` — never `apiRequest` directly, never `fetch`.

**Query-key convention:** array starts with the resource name, then a stable-keyed object of filters or an id. Different filters must produce different keys so they don't share a cache slot, and the resource-name first element makes "invalidate everything for this resource" easy:

```
['bookings', { status, date_from, date_to, limit, offset }]   // collection
['booking', id]                                               // single
['containers', { booking_id }]                                // collection
```

Singular vs plural matters — `['booking', id]` and `['bookings', filters]` are siblings, not the same slot.

**Pagination uses `limit`/`offset`, not `page`.** The backend's `PaginationParams` (`app/schemas/pagination.py`) takes `limit` + `offset`; a `page` param is silently ignored. `useBookings`' `buildPath` emits `limit`/`offset` and its test asserts the built path — keep that assertion when touching filters.

**Idempotency-Key is plumbed for financial POSTs (Phase 4).** It rides `apiRequest`'s existing `headers` option — no client change was needed. Phase 3's mutations stay idempotency-free by design (none produce a unique financial side effect). The customer-payment create passes one; future idempotent endpoints (supplier payment, BL upload) follow the same pattern. See the **Idempotency** section below.

**Customer-payment keys + the prefix-invalidation trick.** Two read hooks scope to a container:

```
['customer-payments', bookingId, containerId]              // tranche list
['customer-payments', bookingId, containerId, 'aggregate'] // rolled-up totals
```

The aggregate key is the list key **plus a trailing `'aggregate'`**, so a single `invalidateQueries({ queryKey: ['customer-payments', bookingId, containerId] })` (a prefix match) refetches _both_. `useCreateCustomerPayment` invalidates that prefix **and** `['booking', bookingId]` (a payment recomputes the container `lifecycle_status`, read off the booking-detail response). Keep the key builders (`customerPaymentsQueryKey`, `customerPaymentAggregateQueryKey`) as the single source of these shapes — the query-key test asserts the prefix relationship.

### Cross-screen data flow

Container detail (`app/(authed)/(tabs)/bookings/[id]/containers/[cid]/index.tsx`) deliberately has no dedicated endpoint — the backend has no `GET /api/v1/containers/{id}`. Containers live as nested objects under `BookingDetailOut.bill_of_lading.containers` and `BookingDetailOut.delivery_points[].containers`. `useContainer` runs `useBooking(bookingId)` under the hood and walks the result for the matching container, deduping when the same id appears in both lists.

This means deep-linking straight to a container URL works (cold cache → loads the parent booking), and tapping through from the booking detail screen is free (warm cache → no extra request). When the backend grows a real `/containers/{id}` endpoint, replace `useContainer`'s body with a direct fetch and drop `findContainerInBooking` — call sites stay the same.

### Status pills

`<StatusPill kind="booking" | "lifecycle" status={…}>` is the single way to render a status badge. The tone mappings (`BOOKING_TONES`, `LIFECYCLE_TONES`) live in `statusPillMapping.ts` next to the component, typed as `Record<EnumType, PillTone>` so missing an enum member fails the typecheck. Tests in `StatusPill.test.ts` belt-and-braces this at runtime. Don't render raw status strings; don't add a second tone-picker anywhere.

**Tones (`PillTone`, Phase 9 — prototype-aligned).** Five tones, each a soft/ink pair: `default` (grey, early/idle), `info` (**blue**, in-flight shipping), `warning` (amber, money in progress), `success` (green, terminal-good), `error` (red, problem). The prototype colors in-flight SHIPPING states **blue**, not amber — so `bl_issued`/`in_transit`/`cleared` + `at_sea`/`arrived`/`import_cleared`/`delivered` → `info`; `invoice_received`/`payment_confirmed`/`invoiced` (money pending) → `warning`; `complete`/`paid`/`banked`/`closed` → `success`; `disputed` → `error`; `draft`/`po_submitted`/`ordered` → `default`. A few were judgment calls where the prototype was silent (noted in the Phase 9 PR): `po_submitted`/`payment_confirmed` and `delivered` (kept in the blue physical-movement family before the amber money phase). Update the `Record<>` **and** `StatusPill.test.ts` in lock-step.

The two enums map to different state-spaces:

- `BookingStatus` — coarse booking lifecycle (`draft → … → complete`).
- `ContainerLifecycleStatus` — per-container end-to-end position (`ordered → at_sea → … → closed`, plus `disputed` as a side-state).

---

## Mutations (writes)

The first write path landed in Phase 3 (container port-status + dispute open/acknowledge). The pattern every future mutation copies:

- **Hooks live in `src/api/mutations/`**, one file per endpoint, shaped `useXxx(bookingId, containerId)` returning a TanStack `useMutation`. The `mutationFn` calls `authedApiRequest<T>(path, { method, body })` — same client as queries, so the 401→refresh→retry-once flow comes for free. Never call `apiRequest`/`fetch` directly. For idempotent financial POSTs, the variables also carry an `idempotencyKey` passed via the `headers` option (see Idempotency).
- **Invalidate-and-refetch on success.** `onSuccess: () => queryClient.invalidateQueries({ queryKey: bookingQueryKey(bookingId) })`. Container state is read out of the booking-detail response (no standalone container endpoint — see Cross-screen data flow), so refetching the booking re-derives the fresh container. A brief refetch spinner is acceptable for an internal tool.
- **The screen wires `onSuccess` per call** (`mutation.mutate(body, { onSuccess })`) for toast + navigation — the hook only owns the request + cache invalidation. Disable the submit button on `mutation.isPending`. For errors, render `mutation.error` (inline `<FormError>` in modal forms, or an `onError` toast on a non-modal screen — see Toasts).
- **Future optimisation (not built):** the dispute open/ack endpoints _return_ the updated `ContainerOut`, so those two could switch to optimistic updates (`setQueryData` on mutate + rollback on error) if the refetch flicker proves annoying. Port-status returns only `{ message }`, so it stays refetch-based regardless. Left as a deliberate later improvement to keep the first write path uniform.
- **Tests** (`src/api/mutations/*.test.ts`) mock `useMutation`/`useQueryClient` + `authedApiRequest` and assert the mutationFn's path/method/body and that `onSuccess` invalidates the right key. No RN renderer (consistent with Testing policy).

### Money (Decimal discipline)

This app handles money; floats silently corrupt it. The rules, enforced from Phase 4 on:

- **Amounts are `string` end-to-end.** Types, form state, and the request body all carry decimal strings (`"1000.50"`) — exactly what the backend's `Decimal` fields (de)serialize as for the create/list (Pydantic) shapes. **Never `parseFloat`/`Number()` a money value for storage or submission.**
- **The one sanctioned float coercion is `parseRatio` in `src/lib/money.ts`**, and only because a progress-bar width is cosmetic and never round-trips to the server. A reviewer greps for stray `parseFloat` — if you need one elsewhere, you're probably doing it wrong.
- **Display via `formatMoney(amount, currency)`** (`src/lib/money.ts`): `"£1,000.50"`, `"—"` for null/masked. It groups thousands _lexically_ (string split, no float maths) so exact digits survive, and accepts `string | number` — the latter because the payments **aggregate** endpoint is the exception below.
- **Total money client-side with `sumDecimalStrings(values)`** (`src/lib/money.ts`), never a `parseFloat` reduce. It sums in integer **cents** (lexical split of each decimal string), skips null/empty entries (masked/absent amounts), and returns a 2-dp decimal string — so `["0.10","0.20"] → "0.30"`, never `0.30000000000000004`. This is the canonical way to roll up a list of amounts (e.g. the supplier-payments per-invoice "Paid X / Y"). The progress-bar ratio still goes through `parseRatio` (the one cosmetic float).
- **"Is it paid/banked?" comes from the backend, not client math.** Use `container.lifecycle_status === 'banked'` (authoritative — the server recomputes it from banked totals vs `sale_price_total`). Don't compare Decimal sums client-side to decide payment state.
- **Backend money-serialization gotcha:** model responses (`CustomerPaymentOut`, `ContainerOut`) serialize `Decimal` → JSON **string**. But the customer-payments **aggregate** route returns a _plain dict_ (no `response_model`), so FastAPI's `jsonable_encoder` serializes its Decimals → JSON **number**. Hence `CustomerPaymentAggregate` is typed with `number` fields and the money helpers accept `string | number`. Watch for this on any future endpoint that returns a bare dict of Decimals.

### Forms (react-hook-form + zod)

The standard for **non-trivial** forms (Phase 4's record-payment form is the reference). Phase 3's ≤3-field forms (dispute reason, port status) stay hand-rolled with `useState` — the threshold is validation complexity, not dogma.

- **Schema + mapper colocated in `src/forms/`.** A zod object validates the form's **all-string** values (so RHF state is uniform and the defaults are clean), and a `toCreateBody(values)` function maps validated values to the typed request body — trimming, omitting blank optionals, and converting non-money counts (e.g. `tranche_index`) to numbers. Money fields pass through as strings.
- **`useForm({ resolver: zodResolver(schema), defaultValues, mode: 'onTouched' })`.** Wrap each field (`Input`, `Select`, `DateField`) in a `<Controller>`; surface `fieldState.error?.message` on the field. Disable submit on `mutation.isPending || !formState.isValid`.
- **Validation mirrors the backend's single-field rules only** — no cross-field validation client-side unless the server has it (the payment endpoint doesn't).
- **zod gotcha (TS 5.5+):** a `.refine((v) => v === 'a' || v === 'b')` predicate is inferred as a _type guard_ and narrows the field's inferred type to the union — which then rejects a `''` default. Use `.refine((v) => ['a','b'].includes(v))` when you want the value to stay `string` (e.g. a Select that starts blank).
- **Modal errors → `<FormError>`, never a toast** (toasts paint behind modals — see Toasts). Success toast fires right before `router.back()`.

### Idempotency

Financial create endpoints **require** an `Idempotency-Key` header (missing → 400). The backend caches the response 24h, so resubmitting with the same key after a lost response returns the cached result instead of creating a duplicate.

- **Generate one key per form mount**, not per tap: `const [idempotencyKey] = useState(() => newIdempotencyKey());` (`src/lib/idempotency.ts`, backed by `expo-crypto`'s synchronous `randomUUID()` — _not_ the non-existent browser `crypto.randomUUID`). Reuse it for every submit of that form session; a fresh open = a fresh key. This is what makes a lost-response retry safe.
- **Pass it via `authedApiRequest`'s `headers` option** in the mutationFn: `{ method: 'POST', body, headers: { 'Idempotency-Key': key } }`. The mutation hook takes the key as a variable (`{ body, idempotencyKey }`) so the screen owns its lifecycle. The mutation test asserts the header is present.
- Applies to: customer payments (Phase 4), supplier payments (Phase 7). Future: BL upload. GETs and idempotent-by-nature writes don't need it.

### Supplier payments (admin-only, invoice-scoped)

Phase 7's mirror of customer payments — money **OUT** (outbound USD wires to the supplier) instead of in. The deltas from the customer-payment pattern:

- **Invoice-scoped, not container-scoped.** `POST`/`GET /api/v1/invoices/{invoiceId}/supplier-payments`. The UI hangs off each PO's `invoice` block on the booking detail screen (`SupplierPaymentsSection`), not the container screen. Read hook `useSupplierPayments(invoiceId, { enabled })`, key `['supplier-payments', invoiceId]`; create hook `useCreateSupplierPayment(invoiceId, bookingId)`.
- **Admin-only on BOTH create and list** (`require_admin`). Unlike customer payments — which let non-admin members _read_ masked amounts — non-admins get a **403 even on the list**. So: the whole section renders only when `user.role === 'admin'`, **and** the list query is gated with `enabled: isAdmin` so a non-admin never fires the doomed request. There is **no** masked-read UI here by design.
- **Status is server-set to `confirmed`** on creation — the client never sends a status and there is **no separate confirm action/endpoint**. One POST is final (contrast the dispute open/ack two-step).
- **Currency is fixed to `"USD"`** — a static label in the form, not an editable field; `toCreateBody` hard-codes it.
- **Auto-advance side effect.** Recording payments whose cumulative total clears the invoices auto-advances the booking `INVOICE_RECEIVED → PAYMENT_CONFIRMED` server-side and notifies. The mobile app does nothing for this beyond invalidating `['booking', bookingId]` in the create mutation's `onSuccess` (alongside the `['supplier-payments', invoiceId]` list) so the lifecycle pill reflects it.
- **Per-invoice progress** = `sumDecimalStrings(payments.map(p => p.amount))` vs the invoice `value` ("Paid X / Y" + `ProgressBar`). No booking-level rollup — the lifecycle pill conveys booking state.
- The `SupplierPaymentOut` shape is identical to the `SupplierPayment` already embedded in `BookingDetailOut.payments`; `src/api/types/supplierPayment.ts` re-exports that type and adds only `SupplierPaymentCreate`. (Phase 7 also removed the old booking-level "Supplier payments" list section, which had been showing masked rows to non-admins — replaced by this admin-only per-invoice section.)

### Toasts

`useToast().showToast(message, tone?: 'success' | 'error' | 'info')` is the feedback channel for **non-modal** screens. `<ToastProvider>` is mounted once at the root (`app/_layout.tsx`, inside `SafeAreaProvider`/`AuthProvider`). It's a hand-rolled `Animated` banner near the bottom (~3s auto-dismiss); calling it again replaces the current toast. Don't add a second snackbar mechanism for routine feedback — `Alert.alert` is reserved for _confirmations_ (e.g. acknowledge-dispute), not result messages.

**Toasts don't show over modal routes.** `presentation: 'modal'` screens are presented in a native layer _above_ the root, so a toast fired while a modal is open is drawn behind it. Two consequences for modal **forms** (port-status, dispute):

- **Success** → call `showToast(...)` then `router.back()`; the toast appears on the detail screen once the modal dismisses. ✓
- **Error** → the form stays open, so use the inline **`<FormError error={mutation.error} fallback="…" />`** banner instead of a toast. (This was caught in Phase 3 device testing — an error toast on an open modal was invisible.)

### Permissions (cosmetic role gating)

`src/auth/permissions.ts` holds pure role-check functions (`canManageDisputes`, `canUpdatePortStatus`, `canManageCustomerPayments`) used to decide which action buttons a screen _shows_. **This is cosmetic only.** The server is the real gate — dispute endpoints are `require_admin` and 403 non-admins regardless of what the UI rendered. Never treat a hidden button as a security boundary. Helpers are null-safe: undefined role denies (restrictive default). Role comes from `useAuth().user?.role`, itself a UI hint decoded from the JWT.

### Modal form routes

Form screens use Expo Router **modal presentation**, declared in the route's nearest layout (`app/(authed)/(tabs)/bookings/_layout.tsx` registers the container form routes — port-status, dispute, record-payment — plus `[id]/add-document` with `options={{ presentation: 'modal' }}`; names are relative to that layout, e.g. `[id]/containers/[cid]/port-status`). Declare presentation in the layout, not via an in-component `<Stack.Screen>` — `presentation` is fixed when the screen mounts. The form reads `id`/`cid` via `useLocalSearchParams`, pre-fills from the relevant query (`useContainer`), submits through a mutation hook, `router.back()`s on success (toast lands on the screen behind), and shows `<FormError>` inline on failure (toasts don't paint over modals — see Toasts). Reuse this pattern for future create/edit forms. Admin-only forms still render a "not permitted" body for a deep-linked non-admin (defense-in-depth; the server is the real gate).

### File uploads (documents)

Documents (PO/invoice/BL/clearing/delivery-schedule/payment attachments) upload via a **presigned-URL flow** — the client never streams bytes through our API. Three steps, all in `useUploadDocument`'s `mutationFn` (`src/api/mutations/useUploadDocument.ts`):

1. **Presign** — `POST /api/v1/documents/upload-url` (body: `entity_type`, `entity_id`, `file_name`, `mime_type`, `file_size_bytes?`) → `{ upload_url, file_key, expires_in_seconds }`.
2. **PUT** — `putFile` (`src/lib/upload.ts`) PUTs the raw bytes straight to `upload_url`. It's the only module that touches native file I/O — it uses **`expo-file-system/legacy`'s `createUploadTask`** (`FileSystemUploadType.BINARY_CONTENT`), because SDK 54's new `File`/`Directory` API has no binary-PUT-with-progress equivalent.
3. **Confirm** — `POST /api/v1/documents/confirm?entity_type=…&entity_id=…` → `DocumentOut`.

Hard rules (the server enforces them too; the client mirrors for UX):

- **`Content-Type` MUST equal the presigned `mime_type` exactly** — it's baked into the R2 signature, so a mismatch makes R2 reject the PUT. Thread one `mime_type` string presign → PUT → confirm. This is the #1 failure cause.
- **`entity_type`/`entity_id` ride the QUERY STRING on confirm**, never the body. The confirm body is only `file_key`/`file_name`/`mime_type`/`file_size_bytes`.
- **NO `Idempotency-Key`** on any document endpoint — unlike the financial create endpoints (`src/lib/idempotency.ts` is _not_ used here). Don't add one.
- **Limits mirror the backend** (`src/lib/files.ts`): 50 MB cap, MIME allowlist (`application/pdf`, `image/jpeg`, `image/png`, `image/webp`, xlsx, `application/vnd.ms-excel`). `validateFile` blocks bad picks client-side before a wasted presign; the server re-checks the object it HEADs in R2 (the source of truth) and 400s/413s regardless.
- **Auth is booking-scoped server-side** — any member of the parent booking can upload/list/view; a non-member gets 403. The client surfaces that gracefully (toast / `<FormError>`); it is not a client gate.

Viewing: `getDownloadUrl(id)` (`src/api/documents/getDownloadUrl.ts`) mints a fresh presigned GET URL on tap (NOT cached — short-lived), opened in the system browser via **lazily-imported `expo-web-browser`**. There's no in-app PDF renderer and no delete endpoint (create + view only).

UI: one reusable **`<DocumentsList entityType entityId label>`** (`src/components/documents/DocumentsList.tsx`) is wired into every sub-entity section on the booking + container detail screens (collapsible "Documents (N)" + Add). It reads the booking `id` from the route (`/bookings/[id]/…`) for navigation, so callers pass only the entity-scoping props. The add-document modal (`app/(authed)/(tabs)/bookings/[id]/add-document.tsx`) **lazily imports `expo-document-picker`/`expo-image-picker` in the pick handlers** (bundle hygiene); the image picker may omit name/mime, so it derives a filename + defaults to `image/jpeg`.

---

## Environment & API base URL

Configured via `EXPO_PUBLIC_API_URL`, consumed only through `import { API_BASE_URL } from '@/src/config/api'`. Never hardcode URLs in components.

| File              | Used by                                           | Committed?          |
| ----------------- | ------------------------------------------------- | ------------------- |
| `.env`            | Local dev defaults                                | yes                 |
| `.env.local`      | Per-machine override (LAN IP for physical device) | **no** (gitignored) |
| `.env.production` | Production build                                  | yes                 |

Production points at `https://api.thefmcghub.com`.

### Physical device LAN IP gotcha

iOS Simulator / Android Emulator can resolve `localhost` to your Mac. **A physical phone running Expo Go cannot** — `localhost` resolves to the phone itself and the backend is unreachable. Fix:

```bash
# in parcel-track-mobile/.env.local (gitignored)
EXPO_PUBLIC_API_URL=http://192.168.x.x:8000
```

Find the IP with `ipconfig getifaddr en0`. Restart `expo start` after changing any `.env*` file — env files are read at bundler startup, not hot-reloaded.

---

## Expo SDK pin

Pinned to **SDK 54** (`expo ~54.0.0`, `react-native 0.81.5`, `react 19.1.0`) because Expo Go in the App Store lagged the SDK 56 release at bootstrap time.

Always read the exact versioned docs at <https://docs.expo.dev/versions/v54.0.0/> before writing Expo-API code — older Stack Overflow answers and the unversioned docs will mislead you.

Bump when a matching Expo Go ships: `npx expo install expo@latest --fix`, then update the SDK number in this section and the docs link.

---

## Common gotchas

| Mistake                                                                                                          | Correct approach                                                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| Raw `fetch(...)` in a screen/hook                                                                                | Always go through `apiRequest` — bypasses 401 refresh, timeout, error normalisation                                                                  |
| `localStorage`, `DOMException`, `window`, `XMLHttpRequest`, `Blob`                                               | None exist in Hermes. Use `expo-secure-store`, `instanceof Error && err.name === 'AbortError'`, etc.                                                 |
| `npm install <expo-package>`                                                                                     | Use `npx expo install <pkg>` for anything Expo-managed — picks the version aligned with your SDK. Plain `npm install` only for non-Expo libs         |
| `npm audit fix --force`                                                                                          | Downgrades `expo` ~10 major versions and breaks the project. Live with the `uuid` advisory (see Known audit noise)                                   |
| Hardcoded `http://...` URL in a component                                                                        | Always import `API_BASE_URL` from `src/config/api`                                                                                                   |
| Tokens in `AsyncStorage`, Redux, or React state                                                                  | `expo-secure-store` only, via `src/auth/tokenStorage.ts`                                                                                             |
| Trusting `user.role` from JWT for security                                                                       | UI hint only. Backend re-checks; handle 403                                                                                                          |
| Editing `.env*` and expecting hot reload                                                                         | Env files are bundler-startup only. Restart `expo start`                                                                                             |
| Logging out on `ApiError.isNetworkError`                                                                         | Transport failure is not an auth failure. Surface "check your connection" instead                                                                    |
| Inline `#hex` colours / magic px in a component                                                                  | Use `src/theme/tokens.ts` (incl. `sizes` for track/dot/icon-box dimensions and `overlays` for rgba scrims)                                           |
| Hand-rolled centered `<Text>` for an empty list, or a text `›`/`▾` chevron                                       | `<EmptyState>` for empty lists; Ionicons `chevron-forward/down/up` for chevrons                                                                      |
| `fontWeight:'700'` (or any `fontWeight`) on a custom-font `<Text>`                                               | Custom RN fonts don't synthesize weight — it renders Regular. Use `<Text weight="semibold">`; family-by-weight resolves via `fontFamily()` (Theme)   |
| Rendering a status string directly or rolling a local `toneFor` helper                                           | Use `<StatusPill kind="booking"                                                                                                                      | "lifecycle" …>` — see Status pills |
| Calling `apiRequest` directly from a screen for authed reads                                                     | Use a query hook in `src/api/queries/` via `useQuery` + `authedApiRequest`                                                                           |
| Calling `apiRequest`/`fetch` from a screen for a write                                                           | Use a mutation hook in `src/api/mutations/` via `useMutation` + `authedApiRequest`; invalidate the parent `['booking', id]` on success               |
| Hiding an admin button and assuming the action is now safe                                                       | Role gating (`src/auth/permissions.ts`) is cosmetic — the server 403s. Handle the error toast, don't rely on the hidden button                       |
| `Alert.alert` / a second snackbar for routine success/error                                                      | Use `useToast().showToast(msg, tone)` — the single feedback channel. `Alert.alert` is for confirmations only                                         |
| `parseFloat`/`Number()` on a money value, or storing it as a number                                              | Money is `string` end-to-end (see Money). The only sanctioned coercion is `parseRatio` for the cosmetic progress bar                                 |
| Deciding "is it banked/paid?" by summing Decimals client-side                                                    | Read `container.lifecycle_status === 'banked'` — the backend recomputes it authoritatively                                                           |
| Generating an `Idempotency-Key` per submit/tap, or via browser `crypto.randomUUID`                               | One key per form mount (`useState(() => newIdempotencyKey())`); `newIdempotencyKey` uses `expo-crypto`                                               |
| Hand-rolling a complex form with `useState`                                                                      | react-hook-form + zod schema in `src/forms/` (see Forms). Hand-rolled is fine only for ≤3 simple fields                                              |
| Uploading a document with a `Content-Type` that differs from the presigned `mime_type`                           | Thread one `mime_type` string presign → PUT → confirm; R2 signs the type, so a mismatch is rejected (see File uploads)                               |
| Putting `entity_type`/`entity_id` in the confirm **body**, or adding an `Idempotency-Key` to a document endpoint | Confirm takes them as **query params**; document endpoints take **no** Idempotency-Key (unlike payments)                                             |
| Importing `expo-document-picker`/`expo-image-picker`/`expo-web-browser` at module top-level                      | Lazy-`import()` them inside the handler that uses them (bundle hygiene — see File uploads)                                                           |
| Reaching for the new `expo-file-system` `File`/`Directory` API for an upload                                     | Use `expo-file-system/legacy`'s `createUploadTask` — the new API has no binary-PUT-with-progress (see `src/lib/upload.ts`)                           |
| Calling `getExpoPushTokenAsync()` without threading `projectId` from `Constants.expoConfig.extra.eas.projectId`  | Pre-EAS / Expo Go works without it, but standalone production builds REQUIRE the projectId. Read it through, never hardcode (see Push notifications) |
| Returning `shouldShowAlert` from `setNotificationHandler` (older docs)                                           | Deprecated in SDK 54. Use `shouldShowBanner` + `shouldShowList` (see Push notifications)                                                             |
| Posting the push token to `/notifications/push-token` as a JSON body                                             | The route takes the token as a **query param** (`?token=…`). `buildPushTokenPath` is the source of truth (see Push notifications)                    |
| Awaiting push registration in the sign-in path                                                                   | Fire-and-forget — never block login UX on a permission denial / network failure (see Push notifications)                                             |

---

## Editor setup

If you open the **monorepo root** (`parcel-tracker/`) in VSCode instead of `parcel-track-mobile/` directly, you'll see phantom red squigglies on every test file: `Cannot find name 'describe'`, `'expect'`, `'jest'`, `'beforeEach'`. Both `npx tsc --noEmit` and CI's `mobile-typecheck` job stay green, so the code is fine — it's the editor's TS server that's misconfigured.

**Why:** VSCode looks for `node_modules/typescript/` at the workspace root to populate "Use Workspace Version." The only TypeScript install in this monorepo lives at `parcel-track-mobile/node_modules/typescript/` (the backend is Python). Without finding a root-level TS, VSCode falls back to its bundled TypeScript, which doesn't auto-include the mobile project's `@types/jest`.

**Fix (already committed at `.vscode/settings.json`):**

```json
{
  "typescript.tsdk": "parcel-track-mobile/node_modules/typescript/lib",
  "typescript.enablePromptUseWorkspaceTsdk": true
}
```

After this file lands, in VSCode: `Cmd+Shift+P → TypeScript: Restart TS Server`. The picker will now offer "Use Workspace Version" pointing at the mobile TS install, and the phantom errors disappear.

If you prefer multi-root or open the mobile folder directly, those work too — the only failure mode is opening the monorepo root _without_ this settings file.

---

## Testing policy

- **Pure-logic + API-client behaviour only**, for now. Anything that doesn't render — JWT decode, error-message extraction, single-flight refresh, token storage helpers — should have a jest test alongside it (`x.test.ts` next to `x.ts`).
- **No UI tests yet.** No `@testing-library/react-native`. UI changes are verified by running the app on simulator + device (see Verification Rules). Add RNTL when the screen count justifies it.
- Mocks live in `src/__mocks__/` (jest auto-discovers). Currently mocks `expo-secure-store` so node-env tests don't try to call native modules.
- Run locally: `npx tsc --noEmit && npm test`. CI runs both on every push touching this directory.

### CI

Single workflow at `../.github/workflows/ci.yml` (monorepo root). Three mobile jobs:

- `mobile-typecheck` — `npm ci` + `npx tsc --noEmit`
- `mobile-test` — `npm ci` + `npm test`
- `mobile-lint` — `npm ci` + `npm run lint` + `npm run format:check`. **Blocking** — see Linting below.

A workflow run executes both backend and mobile jobs regardless of which files changed — accepted cost at this scale.

---

## Linting

ESLint + Prettier, both pinned to the Expo SDK 54 line:

- **ESLint** — flat config (`eslint.config.js`) extending **`eslint-config-expo`** (`~10.0.0`, the SDK-aligned preset; it bundles the react-hooks, react, import and typescript-eslint plugins) with **`eslint-config-prettier`** layered last to disable formatting rules. ESLint owns code quality; Prettier owns formatting.
- **Prettier** — `.prettierrc` captures the de-facto style already in the tree: single quotes, semicolons, trailing commas (`all`), 2-space indent, 100-char print width.
- Run locally: `npm run lint` (and `npm run format:check`). Highest-value signals are `react-hooks/rules-of-hooks` + `exhaustive-deps` in this react-query app.

**Blocking.** The tree was formatted (`prettier --write .`) and lint-cleaned, then `continue-on-error` was dropped from the `mobile-lint` job — so a new ESLint finding or an unformatted file now fails CI. **Run `npm run lint` + `npm run format:check` before pushing**; `npx prettier --write .` fixes formatting in place. The test-file `import/first` rule is disabled in `eslint.config.js` (jest requires `jest.mock(...)` hoisted above imports — see the override).

---

## Deferred fixes

Tracked here so they don't rot inside prose elsewhere.

1. **`/me` endpoint.** When the backend grows it, swap `decodeUserFromToken` for a real fetch and extend `User` with `name` + `email`. Cold-start path becomes a real `/me` call at that point too.
2. **`/containers/{id}` endpoint.** Container detail currently walks the parent booking from cache (see Cross-screen data flow). When the backend grows a dedicated endpoint, replace `useContainer`'s body with a direct fetch and drop `findContainerInBooking`.
3. **UI tests.** Add `@testing-library/react-native` + a couple of smoke tests once there are screens worth covering.
4. **Mutation tooling.** ✅ Landed: toast/snackbar (Phase 3); react-hook-form + zod form library and `Idempotency-Key` plumbing (Phase 4). See Forms / Idempotency / Money.
5. **EAS Build profile.** Not configured yet — first production build will need `eas.json` + credentials.
6. **Payments masking UX.** Non-admins get null amounts back; the section shows a single "Amounts hidden for your role" hint. Revisit if a richer masked view is wanted.
7. **Make lint blocking.** ✅ Done — the tree was formatted + lint-cleaned and `mobile-lint` is now a hard gate. See Linting.

---

## Known `npm audit` noise

`npm audit` reports 12 moderate vulnerabilities, all transitively from `uuid < 11.1.1` ([GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq)). Path: `uuid → xcode → @expo/config-plugins → … → expo`.

**Do not run `npm audit fix --force`** — it downgrades `expo` by ~10 major versions and breaks everything. The vulnerable code is build-time only (`xcode`, used during `expo prebuild` / EAS Build); it does not ship in the app bundle and no attacker-controlled input reaches it. Wait for upstream `xcode` / Expo to bump `uuid`.
