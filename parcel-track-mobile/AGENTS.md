# AGENTS.md — parcel-track-mobile

_Last reviewed: 2026-05-31. The Expo SDK pin and any "current state" notes below go stale fast — update this date whenever you touch them._

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
- Read the actual error: stack trace, Metro logs, device console. For network bugs, check `ApiError.status` (transport failures use `NETWORK_ERROR_STATUS = 0`) and `ApiError.payload` before guessing.
- Trace to root cause. Don't paper over symptoms with a `try/catch` that swallows.
- Only ask clarifying questions when the cause is genuinely undetermined after looking.

## Task Management Rules

- Write a plan to `tasks/todo.md` before any non-trivial implementation. Mark items done as you go.
- After a correction from the user, append the lesson to `tasks/lessons.md` (create it if missing). Re-read it at the start of every session.
- Never start a new task without updating the task file.

## Verification Rules

- Pure-logic changes (api client, auth, jwt, utils): `npx tsc --noEmit` + `npm test` must pass before reporting done.
- UI changes: typecheck + tests, **and** actually run the app on the iOS simulator (or device via Expo Go) and confirm the change renders + behaves as intended. Screenshot when useful. UI work is not "done" because tests pass — there aren't UI tests yet (see Testing policy).
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

| Layer | Technology |
|---|---|
| Framework | Expo SDK 54 (pinned — see Expo SDK pin note below) |
| Runtime | React Native 0.81, React 19.1, Hermes |
| Language | TypeScript ~5.9 (strict; no DOM lib used) |
| Auth storage | `expo-secure-store` |
| JWT decode (UI only) | `jwt-decode` |
| HTTP | native `fetch`, wrapped by `src/api/client.ts` |
| Tests | jest 29 + ts-jest (node env, pure-logic only) |
| Navigation | Expo Router (file-based; routes under `app/`, route groups `(auth)` + `(authed)`; the signed-in area is a bottom-tab navigator under `(authed)/(tabs)`) |
| Server state | TanStack Query — `QueryClientProvider` in `app/_layout.tsx`; hooks in `src/api/queries/` |
| Client state | React Context only (`AuthContext`). No Redux/Zustand until there's a concrete need |
| Env loading | `expo` reads `.env`, `.env.local`, `.env.production` at bundler start |

---

## Architecture invariants

- **One HTTP client.** `apiRequest<T>(path, options)` in `src/api/client.ts` is the only function that calls `fetch`. It owns: base-URL prefixing, JSON content negotiation, bearer-token injection, 15 s default timeout, uniform `ApiError`, and the 401→refresh→retry-once flow.
- **Auth-endpoint calls opt out.** Login and refresh itself pass `auth: 'skip'` to `apiRequest` — a 401 there means bad creds / dead refresh token and must propagate, not trigger another refresh.
- **Single-flight refresh.** N concurrent 401s run exactly one `POST /api/v1/auth/refresh`. Don't add a parallel path.
- **Session-expired is an event, not a return value.** On refresh failure, `client.ts` calls `clearTokens()` and `emitSessionExpired()` (`src/auth/sessionEvents.ts`). `AuthProvider` listens and flips status → `anonymous`, which re-renders the login screen. Don't try to navigate from inside the API client.
- **`AuthContext` is the only consumer of token storage.** Screens read `useAuth()` for `{ status, user, signIn, signOut }` — they don't call `getAccessToken()` themselves.
- **Theme tokens, not inline styles.** Colours, spacing, radii live in `src/theme/tokens.ts` and are consumed via `src/theme/index.ts`. Hard-coded hex/px in a component is a code-smell.
- **Shared UI primitives in `src/components/ui/`.** `Button`, `Card`, `FormError`, `Input`, `ListItem`, `Pill`, `ScreenContainer`, `Select`, `Spinner`, `StatusPill`, `Text`, plus the `ToastProvider`/`useToast` feedback system. Reach for these before building bespoke views.
- **One status-pill component.** Any badge that renders a `BookingStatus` or `ContainerLifecycleStatus` goes through `<StatusPill>` (`src/components/ui/StatusPill.tsx`). It maps each enum value to a tone via an exhaustive `Record<...>` — a new backend enum value will fail TS until the mapping in `statusPillMapping.ts` is updated. Don't render raw status strings, and don't reimplement a local tone-picker.

---

## Folder map

| Folder | What lives here | Example |
|---|---|---|
| `app/` | Expo Router routes. Route groups `(auth)` (anon-only) + `(authed)` (signed-in); the signed-in area is the bottom-tab group `(authed)/(tabs)` (Dashboard / Bookings / Alerts). Each folder has a `_layout.tsx` for its guard/navigator | `app/(authed)/(tabs)/bookings/[id]/index.tsx` |
| `src/api/` | HTTP client + typed endpoint wrappers + React-hook-shaped queries | `client.ts`, `authedClient.ts`, `queries/useBookings.ts`, `queries/useBooking.ts` |
| `src/api/queries/` | TanStack Query read hooks | `useBookings.ts`, `useBooking.ts`, `useContainer.ts` |
| `src/api/mutations/` | TanStack Query write hooks (invalidate-and-refetch) | `useUpdatePortStatus.ts`, `useOpenDispute.ts`, `useCreateCustomerPayment.ts` |
| `src/api/types/` | Hand-typed TS mirrors of backend Pydantic schemas. Split per domain | `booking.ts`, `container.ts`, `enums.ts` |
| `src/auth/` | Auth state machine, token storage, JWT decode, session events, role gating | `AuthContext.tsx`, `tokenStorage.ts`, `jwt.ts`, `sessionEvents.ts`, `authApi.ts`, `permissions.ts` |
| `src/components/` | Cross-cutting components that compose primitives | `AppHeader.tsx` |
| `src/components/ui/` | Reusable presentational primitives — no network, no storage | `Button.tsx`, `Card.tsx`, `StatusPill.tsx`, `ScreenContainer.tsx` |
| `src/config/` | Env-derived constants. Single export per concern | `api.ts` (`API_BASE_URL`) |
| `src/theme/` | Design tokens + theme helpers | `tokens.ts`, `index.ts` |
| `src/lib/` | Framework-agnostic pure helpers (no React, no network) | `money.ts`, `idempotency.ts` |
| `src/forms/` | zod schemas + form→body mappers for non-trivial forms | `customerPaymentSchema.ts` |
| `src/__mocks__/` | Jest manual mocks for native modules that don't run in node | `expo-secure-store.ts`, `expo-crypto.ts` |
| _(future)_ `src/hooks/` | Cross-screen hooks that aren't tied to a single domain | — |

Tests sit next to the file under test (`client.test.ts` next to `client.ts`), not in a parallel tree.

Two more `src/` areas exist as of Phase 5: `src/features/dashboard/` (role→sections selector + dashboard view components) and `src/features/alerts/` (notification label/tone map). Feature-scoped UI + pure helpers that aren't a reusable primitive live under `src/features/<domain>/`.

---

## Navigation (bottom tabs + nested Bookings stack)

The signed-in area is a **bottom-tab navigator** with three destinations:

```
app/(authed)/_layout.tsx              # auth guard → Stack (headerShown:false); renders (tabs)
app/(authed)/(tabs)/_layout.tsx       # <Tabs>: Dashboard | Bookings | Alerts (+ unread badge)
app/(authed)/(tabs)/index.tsx         # Dashboard (role-aware home — see Dashboards)
app/(authed)/(tabs)/alerts.tsx        # Alerts feed (see Notifications)
app/(authed)/(tabs)/bookings/_layout.tsx   # <Stack> for the Bookings tab; registers the 3 modals
app/(authed)/(tabs)/bookings/**            # list → [id] detail → containers/[cid] → modals
```

- **Where new screens go.** A new *top-level destination* is a tab (a file/dir under `(tabs)` + a `<Tabs.Screen>`). A new *bookings detail/form screen* goes inside the Bookings-tab stack (`(tabs)/bookings/…`) so it pushes within that tab.
- **Modals live in the Bookings-tab stack.** `presentation: 'modal'` for port-status / dispute / record-payment is declared in `(authed)/(tabs)/bookings/_layout.tsx` (names relative to it, e.g. `[id]/containers/[cid]/port-status`) — **not** in `(authed)/_layout.tsx` anymore.
- **Route groups are invisible in the URL.** `(authed)` and `(tabs)` are parenthesised groups, so a booking's URL stays `/bookings/{id}` regardless of nesting — existing `router.push('/bookings/…')` / `/(authed)/bookings/…` hrefs kept working through the restructure untouched. Switch tabs with a plain href (`router.push('/alerts')`).
- **Cold start lands on the Dashboard tab** (`(tabs)/index.tsx`); the old `(authed)/index.tsx` redirect was deleted.

### Path alias `@/`

`tsconfig.json` maps `@/* → ./*`. **`app/` files use the `@/` alias** (`@/src/...`) — verified to resolve under both `npx tsc --noEmit` and a real `npx expo export` bundle on SDK 54 (Expo's Metro reads tsconfig `paths`; there is no `baseUrl` — that was the Phase 1 footgun). **`src/` files keep relative imports**, because `jest.config.js` has no `@/` moduleNameMapper and the existing tests mock relative paths; keeping `src/` relative means no jest change is needed. (`@expo/vector-icons` is an explicit dependency so tsc can resolve its types — it was previously only transitively present under `expo/node_modules`, which Metro resolves but tsc does not.)

## Dashboards (role-aware home)

`(tabs)/index.tsx` is **one** screen driven by `dashboardConfig(role)` (`src/features/dashboard/dashboardSections.ts`, pure + tested) rather than four near-duplicate role components — the role differences (greeting label, which status count-cards to emphasize, empty copy) are pure data.

- **Greeting is the role label only** — there is no `/me` endpoint and the JWT carries no name.
- **Status counts are client-side.** The bookings list has no faceted-count endpoint, so the dashboard does one `useBookings({ limit: 200 })` and groups with `countByStatus` (`src/lib/bookingStatusCounts.ts`). Caps at one page; the volume upgrade is N `status=X&limit=1` calls reading `total`.
- **Booking grain only.** There is no cross-booking container endpoint, so dashboards summarize *bookings* (e.g. the UK agent sees their in-transit / cleared bookings); drill into a booking for its containers.
- Count cards + the alerts teaser navigate to the Bookings / Alerts tabs (no status filter on the list yet).

## Notifications (alerts feed)

Endpoints (`parcel-track/app/api/routes/notifications.py`):

- `GET /api/v1/notifications?unread_only=&limit=&offset=` → `PaginatedResponse<NotificationOut>` (`useNotifications`, key `['notifications', filters]`).
- **`PATCH`** `/api/v1/notifications/{id}/read` (no body) → `{ message }` (`useMarkNotificationRead`). It is PATCH, **not** POST.
- There is **no** `/unread-count` and **no** mark-all-read endpoint. The tab badge derives the count from `GET …?unread_only=true&limit=1` → `.total` (`useUnreadCount`, key `['notifications', 'unread-count']`).
- **Prefix invalidation:** `useMarkNotificationRead` invalidates the bare `['notifications']` prefix — one call refetches every list query *and* the unread-count badge (both sit under that prefix).
- **`NotificationOut`** = `{ id, type, title, message, read, booking_id, created_at }` — the field is `message` (not `body`), and the only entity reference is `booking_id` (nullable). So a row **deep-links to `/bookings/{booking_id}` when set**, and is mark-read-only otherwise (no `entity_type`/`entity_id` exist).
- **`NotificationType`** has 15 values (mirror in `src/api/types/enums.ts`); `NOTIFICATION_LABELS`/`NOTIFICATION_TONES` (`src/features/alerts/notificationDisplay.ts`) map each exhaustively — a new backend value fails the typecheck until added.

---

## API client error contract

Every call through `apiRequest` either resolves with the parsed JSON body (typed via the caller's `<T>`) or throws an `ApiError`. There is no third shape.

```ts
class ApiError extends Error {
  readonly status: number;       // HTTP status, or 0 for transport-level failure
  readonly payload: unknown;     // parsed response body (or original error for status === 0)
  readonly isNetworkError: boolean;  // true iff status === 0
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

The aggregate key is the list key **plus a trailing `'aggregate'`**, so a single `invalidateQueries({ queryKey: ['customer-payments', bookingId, containerId] })` (a prefix match) refetches *both*. `useCreateCustomerPayment` invalidates that prefix **and** `['booking', bookingId]` (a payment recomputes the container `lifecycle_status`, read off the booking-detail response). Keep the key builders (`customerPaymentsQueryKey`, `customerPaymentAggregateQueryKey`) as the single source of these shapes — the query-key test asserts the prefix relationship.

### Cross-screen data flow

Container detail (`app/(authed)/(tabs)/bookings/[id]/containers/[cid]/index.tsx`) deliberately has no dedicated endpoint — the backend has no `GET /api/v1/containers/{id}`. Containers live as nested objects under `BookingDetailOut.bill_of_lading.containers` and `BookingDetailOut.delivery_points[].containers`. `useContainer` runs `useBooking(bookingId)` under the hood and walks the result for the matching container, deduping when the same id appears in both lists.

This means deep-linking straight to a container URL works (cold cache → loads the parent booking), and tapping through from the booking detail screen is free (warm cache → no extra request). When the backend grows a real `/containers/{id}` endpoint, replace `useContainer`'s body with a direct fetch and drop `findContainerInBooking` — call sites stay the same.

### Status pills

`<StatusPill kind="booking" | "lifecycle" status={…}>` is the single way to render a status badge. The tone mappings (`BOOKING_TONES`, `LIFECYCLE_TONES`) live in `statusPillMapping.ts` next to the component, typed as `Record<EnumType, PillTone>` so missing an enum member fails the typecheck. Tests in `StatusPill.test.ts` belt-and-braces this at runtime. Don't render raw status strings; don't add a second tone-picker anywhere.

The two enums map to different state-spaces:
- `BookingStatus` — coarse booking lifecycle (`draft → … → complete`).
- `ContainerLifecycleStatus` — per-container end-to-end position (`ordered → at_sea → … → closed`, plus `disputed` as a side-state).

---

## Mutations (writes)

The first write path landed in Phase 3 (container port-status + dispute open/acknowledge). The pattern every future mutation copies:

- **Hooks live in `src/api/mutations/`**, one file per endpoint, shaped `useXxx(bookingId, containerId)` returning a TanStack `useMutation`. The `mutationFn` calls `authedApiRequest<T>(path, { method, body })` — same client as queries, so the 401→refresh→retry-once flow comes for free. Never call `apiRequest`/`fetch` directly. For idempotent financial POSTs, the variables also carry an `idempotencyKey` passed via the `headers` option (see Idempotency).
- **Invalidate-and-refetch on success.** `onSuccess: () => queryClient.invalidateQueries({ queryKey: bookingQueryKey(bookingId) })`. Container state is read out of the booking-detail response (no standalone container endpoint — see Cross-screen data flow), so refetching the booking re-derives the fresh container. A brief refetch spinner is acceptable for an internal tool.
- **The screen wires `onSuccess` per call** (`mutation.mutate(body, { onSuccess })`) for toast + navigation — the hook only owns the request + cache invalidation. Disable the submit button on `mutation.isPending`. For errors, render `mutation.error` (inline `<FormError>` in modal forms, or an `onError` toast on a non-modal screen — see Toasts).
- **Future optimisation (not built):** the dispute open/ack endpoints *return* the updated `ContainerOut`, so those two could switch to optimistic updates (`setQueryData` on mutate + rollback on error) if the refetch flicker proves annoying. Port-status returns only `{ message }`, so it stays refetch-based regardless. Left as a deliberate later improvement to keep the first write path uniform.
- **Tests** (`src/api/mutations/*.test.ts`) mock `useMutation`/`useQueryClient` + `authedApiRequest` and assert the mutationFn's path/method/body and that `onSuccess` invalidates the right key. No RN renderer (consistent with Testing policy).

### Money (Decimal discipline)

This app handles money; floats silently corrupt it. The rules, enforced from Phase 4 on:

- **Amounts are `string` end-to-end.** Types, form state, and the request body all carry decimal strings (`"1000.50"`) — exactly what the backend's `Decimal` fields (de)serialize as for the create/list (Pydantic) shapes. **Never `parseFloat`/`Number()` a money value for storage or submission.**
- **The one sanctioned float coercion is `parseRatio` in `src/lib/money.ts`**, and only because a progress-bar width is cosmetic and never round-trips to the server. A reviewer greps for stray `parseFloat` — if you need one elsewhere, you're probably doing it wrong.
- **Display via `formatMoney(amount, currency)`** (`src/lib/money.ts`): `"£1,000.50"`, `"—"` for null/masked. It groups thousands *lexically* (string split, no float maths) so exact digits survive, and accepts `string | number` — the latter because the payments **aggregate** endpoint is the exception below.
- **"Is it paid/banked?" comes from the backend, not client math.** Use `container.lifecycle_status === 'banked'` (authoritative — the server recomputes it from banked totals vs `sale_price_total`). Don't compare Decimal sums client-side to decide payment state.
- **Backend money-serialization gotcha:** model responses (`CustomerPaymentOut`, `ContainerOut`) serialize `Decimal` → JSON **string**. But the customer-payments **aggregate** route returns a *plain dict* (no `response_model`), so FastAPI's `jsonable_encoder` serializes its Decimals → JSON **number**. Hence `CustomerPaymentAggregate` is typed with `number` fields and the money helpers accept `string | number`. Watch for this on any future endpoint that returns a bare dict of Decimals.

### Forms (react-hook-form + zod)

The standard for **non-trivial** forms (Phase 4's record-payment form is the reference). Phase 3's ≤3-field forms (dispute reason, port status) stay hand-rolled with `useState` — the threshold is validation complexity, not dogma.

- **Schema + mapper colocated in `src/forms/`.** A zod object validates the form's **all-string** values (so RHF state is uniform and the defaults are clean), and a `toCreateBody(values)` function maps validated values to the typed request body — trimming, omitting blank optionals, and converting non-money counts (e.g. `tranche_index`) to numbers. Money fields pass through as strings.
- **`useForm({ resolver: zodResolver(schema), defaultValues, mode: 'onTouched' })`.** Wrap each field (`Input`, `Select`, `DateField`) in a `<Controller>`; surface `fieldState.error?.message` on the field. Disable submit on `mutation.isPending || !formState.isValid`.
- **Validation mirrors the backend's single-field rules only** — no cross-field validation client-side unless the server has it (the payment endpoint doesn't).
- **zod gotcha (TS 5.5+):** a `.refine((v) => v === 'a' || v === 'b')` predicate is inferred as a *type guard* and narrows the field's inferred type to the union — which then rejects a `''` default. Use `.refine((v) => ['a','b'].includes(v))` when you want the value to stay `string` (e.g. a Select that starts blank).
- **Modal errors → `<FormError>`, never a toast** (toasts paint behind modals — see Toasts). Success toast fires right before `router.back()`.

### Idempotency

Financial create endpoints **require** an `Idempotency-Key` header (missing → 400). The backend caches the response 24h, so resubmitting with the same key after a lost response returns the cached result instead of creating a duplicate.

- **Generate one key per form mount**, not per tap: `const [idempotencyKey] = useState(() => newIdempotencyKey());` (`src/lib/idempotency.ts`, backed by `expo-crypto`'s synchronous `randomUUID()` — *not* the non-existent browser `crypto.randomUUID`). Reuse it for every submit of that form session; a fresh open = a fresh key. This is what makes a lost-response retry safe.
- **Pass it via `authedApiRequest`'s `headers` option** in the mutationFn: `{ method: 'POST', body, headers: { 'Idempotency-Key': key } }`. The mutation hook takes the key as a variable (`{ body, idempotencyKey }`) so the screen owns its lifecycle. The mutation test asserts the header is present.
- Applies to: customer payments (Phase 4). Future: supplier payments, BL upload. GETs and idempotent-by-nature writes don't need it.

### Toasts

`useToast().showToast(message, tone?: 'success' | 'error' | 'info')` is the feedback channel for **non-modal** screens. `<ToastProvider>` is mounted once at the root (`app/_layout.tsx`, inside `SafeAreaProvider`/`AuthProvider`). It's a hand-rolled `Animated` banner near the bottom (~3s auto-dismiss); calling it again replaces the current toast. Don't add a second snackbar mechanism for routine feedback — `Alert.alert` is reserved for *confirmations* (e.g. acknowledge-dispute), not result messages.

**Toasts don't show over modal routes.** `presentation: 'modal'` screens are presented in a native layer *above* the root, so a toast fired while a modal is open is drawn behind it. Two consequences for modal **forms** (port-status, dispute):
- **Success** → call `showToast(...)` then `router.back()`; the toast appears on the detail screen once the modal dismisses. ✓
- **Error** → the form stays open, so use the inline **`<FormError error={mutation.error} fallback="…" />`** banner instead of a toast. (This was caught in Phase 3 device testing — an error toast on an open modal was invisible.)

### Permissions (cosmetic role gating)

`src/auth/permissions.ts` holds pure role-check functions (`canManageDisputes`, `canUpdatePortStatus`, `canManageCustomerPayments`) used to decide which action buttons a screen *shows*. **This is cosmetic only.** The server is the real gate — dispute endpoints are `require_admin` and 403 non-admins regardless of what the UI rendered. Never treat a hidden button as a security boundary. Helpers are null-safe: undefined role denies (restrictive default). Role comes from `useAuth().user?.role`, itself a UI hint decoded from the JWT.

### Modal form routes

Form screens use Expo Router **modal presentation**, declared in the route's nearest layout (`app/(authed)/(tabs)/bookings/_layout.tsx` registers the three container form routes — port-status, dispute, record-payment — with `options={{ presentation: 'modal' }}`; names are relative to that layout, e.g. `[id]/containers/[cid]/port-status`). Declare presentation in the layout, not via an in-component `<Stack.Screen>` — `presentation` is fixed when the screen mounts. The form reads `id`/`cid` via `useLocalSearchParams`, pre-fills from the relevant query (`useContainer`), submits through a mutation hook, `router.back()`s on success (toast lands on the screen behind), and shows `<FormError>` inline on failure (toasts don't paint over modals — see Toasts). Reuse this pattern for future create/edit forms. Admin-only forms still render a "not permitted" body for a deep-linked non-admin (defense-in-depth; the server is the real gate).

---

## Environment & API base URL

Configured via `EXPO_PUBLIC_API_URL`, consumed only through `import { API_BASE_URL } from '@/src/config/api'`. Never hardcode URLs in components.

| File | Used by | Committed? |
|---|---|---|
| `.env` | Local dev defaults | yes |
| `.env.local` | Per-machine override (LAN IP for physical device) | **no** (gitignored) |
| `.env.production` | Production build | yes |

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

| Mistake | Correct approach |
|---|---|
| Raw `fetch(...)` in a screen/hook | Always go through `apiRequest` — bypasses 401 refresh, timeout, error normalisation |
| `localStorage`, `DOMException`, `window`, `XMLHttpRequest`, `Blob` | None exist in Hermes. Use `expo-secure-store`, `instanceof Error && err.name === 'AbortError'`, etc. |
| `npm install <expo-package>` | Use `npx expo install <pkg>` for anything Expo-managed — picks the version aligned with your SDK. Plain `npm install` only for non-Expo libs |
| `npm audit fix --force` | Downgrades `expo` ~10 major versions and breaks the project. Live with the `uuid` advisory (see Known audit noise) |
| Hardcoded `http://...` URL in a component | Always import `API_BASE_URL` from `src/config/api` |
| Tokens in `AsyncStorage`, Redux, or React state | `expo-secure-store` only, via `src/auth/tokenStorage.ts` |
| Trusting `user.role` from JWT for security | UI hint only. Backend re-checks; handle 403 |
| Editing `.env*` and expecting hot reload | Env files are bundler-startup only. Restart `expo start` |
| Logging out on `ApiError.isNetworkError` | Transport failure is not an auth failure. Surface "check your connection" instead |
| Inline `#hex` colours / magic px in a component | Use `src/theme/tokens.ts` |
| Rendering a status string directly or rolling a local `toneFor` helper | Use `<StatusPill kind="booking" | "lifecycle" …>` — see Status pills |
| Calling `apiRequest` directly from a screen for authed reads | Use a query hook in `src/api/queries/` via `useQuery` + `authedApiRequest` |
| Calling `apiRequest`/`fetch` from a screen for a write | Use a mutation hook in `src/api/mutations/` via `useMutation` + `authedApiRequest`; invalidate the parent `['booking', id]` on success |
| Hiding an admin button and assuming the action is now safe | Role gating (`src/auth/permissions.ts`) is cosmetic — the server 403s. Handle the error toast, don't rely on the hidden button |
| `Alert.alert` / a second snackbar for routine success/error | Use `useToast().showToast(msg, tone)` — the single feedback channel. `Alert.alert` is for confirmations only |
| `parseFloat`/`Number()` on a money value, or storing it as a number | Money is `string` end-to-end (see Money). The only sanctioned coercion is `parseRatio` for the cosmetic progress bar |
| Deciding "is it banked/paid?" by summing Decimals client-side | Read `container.lifecycle_status === 'banked'` — the backend recomputes it authoritatively |
| Generating an `Idempotency-Key` per submit/tap, or via browser `crypto.randomUUID` | One key per form mount (`useState(() => newIdempotencyKey())`); `newIdempotencyKey` uses `expo-crypto` |
| Hand-rolling a complex form with `useState` | react-hook-form + zod schema in `src/forms/` (see Forms). Hand-rolled is fine only for ≤3 simple fields |

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

If you prefer multi-root or open the mobile folder directly, those work too — the only failure mode is opening the monorepo root *without* this settings file.

---

## Testing policy

- **Pure-logic + API-client behaviour only**, for now. Anything that doesn't render — JWT decode, error-message extraction, single-flight refresh, token storage helpers — should have a jest test alongside it (`x.test.ts` next to `x.ts`).
- **No UI tests yet.** No `@testing-library/react-native`. UI changes are verified by running the app on simulator + device (see Verification Rules). Add RNTL when the screen count justifies it.
- Mocks live in `src/__mocks__/` (jest auto-discovers). Currently mocks `expo-secure-store` so node-env tests don't try to call native modules.
- Run locally: `npx tsc --noEmit && npm test`. CI runs both on every push touching this directory.

### CI

Single workflow at `../.github/workflows/ci.yml` (monorepo root). Two mobile jobs:

- `mobile-typecheck` — `npm ci` + `npx tsc --noEmit`
- `mobile-test` — `npm ci` + `npm test`

A workflow run executes both backend and mobile jobs regardless of which files changed — accepted cost at this scale. No mobile lint yet; add when there's a style worth enforcing.

---

## Deferred fixes

Tracked here so they don't rot inside prose elsewhere.

1. **`/me` endpoint.** When the backend grows it, swap `decodeUserFromToken` for a real fetch and extend `User` with `name` + `email`. Cold-start path becomes a real `/me` call at that point too.
2. **`/containers/{id}` endpoint.** Container detail currently walks the parent booking from cache (see Cross-screen data flow). When the backend grows a dedicated endpoint, replace `useContainer`'s body with a direct fetch and drop `findContainerInBooking`.
3. **UI tests.** Add `@testing-library/react-native` + a couple of smoke tests once there are screens worth covering.
4. **Mutation tooling.** ✅ Landed: toast/snackbar (Phase 3); react-hook-form + zod form library and `Idempotency-Key` plumbing (Phase 4). See Forms / Idempotency / Money.
5. **EAS Build profile.** Not configured yet — first production build will need `eas.json` + credentials.
6. **Payments masking UX.** Non-admins get null amounts back; the section shows a single "Amounts hidden for your role" hint. Revisit if a richer masked view is wanted.

---

## Known `npm audit` noise

`npm audit` reports 10 moderate vulnerabilities, all transitively from `uuid < 11.1.1` ([GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq)). Path: `uuid → xcode → @expo/config-plugins → … → expo`.

**Do not run `npm audit fix --force`** — it downgrades `expo` by ~10 major versions and breaks everything. The vulnerable code is build-time only (`xcode`, used during `expo prebuild` / EAS Build); it does not ship in the app bundle and no attacker-controlled input reaches it. Wait for upstream `xcode` / Expo to bump `uuid`.
