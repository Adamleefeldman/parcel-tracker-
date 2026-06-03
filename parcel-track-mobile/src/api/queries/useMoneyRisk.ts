/**
 * Money-risk dashboard query — the data behind the "Alerts" tab and the
 * Bookings-tab hero cards.
 *
 * GET /api/v1/money-risk → MoneyRiskOut { ar_aging, demurrage, disputes }.
 * Auth: **require_role(ADMIN, UK_AGENT)** — Morocco agent and customer get a
 * 403. So the caller passes `enabled: canSeeMoneyRisk(role)`, gating the query
 * the same way `useSupplierPayments` gates its admin-only read: a hidden-tab
 * role never fires the doomed request. The tab itself is also hidden via
 * `href: null` for those roles (cosmetic), but the `enabled` gate is what stops
 * the network call.
 *
 * Query-key convention: resource name only — there are no filters, the whole
 * dashboard comes in one call. `['money-risk']`.
 */

import { useQuery } from '@tanstack/react-query';

import type { MoneyRiskOut } from '../types/moneyRisk';
import { authedApiRequest } from '../authedClient';

export function moneyRiskQueryKey(): readonly unknown[] {
  return ['money-risk'] as const;
}

/**
 * The two roles the endpoint allows (mirrors the backend `require_role`).
 * Takes the raw JWT `role` string (a UI hint — see AGENTS.md), so it's null-safe
 * and an unknown/undefined role denies (restrictive default).
 */
export function canSeeMoneyRisk(role: string | undefined): boolean {
  return role === 'admin' || role === 'uk_agent';
}

export function useMoneyRisk(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: moneyRiskQueryKey(),
    queryFn: () => authedApiRequest<MoneyRiskOut>('/api/v1/money-risk'),
    // Default true so an omitted option behaves like the other read hooks, but
    // callers always pass `enabled: canSeeMoneyRisk(role)` (the endpoint 403s
    // morocco_agent / customer).
    enabled: options?.enabled ?? true,
  });
}
