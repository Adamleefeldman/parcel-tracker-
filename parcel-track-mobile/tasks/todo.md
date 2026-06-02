# Hardening PR A — crash safety, correctness & screen code-quality

Branch: `mobile-harden-crash-safety`. Diff stays under `app/` + `src/`. No new deps.

## High (must-haves)
- [x] #1 Root error boundary — `export function ErrorBoundary` in `app/_layout.tsx` (fallback + retry).
- [x] #2 Null-guard top-level arrays in booking detail (`legs`, `purchase_orders`, `delivery_points`) — `?? []`.
- [x] #3 Pagination correctness
  - [x] Supplier payments per-invoice sum: high limit (500) + "(partial)" / "showing N of total" marker.
  - [x] Bookings list / alerts: "first N of {total}" truncation footer.
  - [x] Documents: list already shows total via header "Documents (N)"; no truncation in practice (left as-is, count surfaced).
  - [x] Dashboard status counts: "{n}+ of {total}" approximate label when total > fetched page.

## Medium
- [x] #4 Dashboard surfaces notification errors in `AlertsSummaryCard` (error pill + Retry).
- [x] #5 KeyboardAvoidingView on modal forms: record-payment, record-supplier-payment, dispute, port-status. (add-document has no text inputs — KAV not needed.)
- [x] #6 Upload "Finalising…" phase + indeterminate spinner fallback when total bytes unknown.

## Code-quality
- [x] #7 `src/lib/date.ts` (noon-parse) + `date.test.ts` (no-day-shift). Replaced 4 inline copies.
- [x] #8 Route booking-detail money through `formatMoney`.
- [x] #9 Extracted `src/components/ui/ErrorState.tsx`; replaced 5 copies.
- [x] #10 Booking-detail tokens; added `colors.errorSurface`; used in dispute card, add-document, FormError, Pill.

## Reuse / cleanup
- [x] Fixed the 2 prefixed router hrefs (`/(authed)/bookings/...` → `/bookings/...`).

## Verify
- [x] `npx tsc --noEmit` clean; `npm test` green (190 tests, +9 date).
- [ ] PR body: device checklist (verbatim), payment-sum check emphasized, sibling PR B note.
