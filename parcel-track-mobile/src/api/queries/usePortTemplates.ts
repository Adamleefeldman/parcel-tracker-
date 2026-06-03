/**
 * Port-templates list query (admin "Operations").
 *
 * GET /api/v1/port-templates → `PortTemplate[]` — a plain list (NOT paginated;
 * one row per saved UK port, ≤6). List is open to any authenticated user; the
 * screen is admin-only, so callers pass `enabled: isAdmin`.
 *
 * Key shape: resource name only — there are no filters. `['port-templates']`,
 * matching the `useMoneyRisk` single-slot convention. Note the screen renders
 * EVERY `UKPort` (defaults shown for ports with no saved row), so a port absent
 * from this array is "not set", not an error.
 */

import { useQuery } from '@tanstack/react-query';

import type { PortTemplate } from '../types/admin';
import { authedApiRequest } from '../authedClient';

export function portTemplatesQueryKey(): readonly unknown[] {
  return ['port-templates'] as const;
}

export function usePortTemplates(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: portTemplatesQueryKey(),
    queryFn: () => authedApiRequest<PortTemplate[]>('/api/v1/port-templates'),
    enabled: options?.enabled ?? true,
  });
}
