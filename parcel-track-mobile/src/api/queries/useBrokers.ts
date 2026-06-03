/**
 * Brokers list query (admin "Operations").
 *
 * GET /api/v1/brokers → PaginatedResponse<Broker>. The list endpoint is open to
 * any authenticated user, but the screen is admin-only, so callers pass
 * `enabled: isAdmin` — a deep-linked non-admin never fires the request. Key
 * shape follows the codebase convention: resource name + stable filters object.
 *
 * Pagination uses `limit`/`offset` (the backend's `PaginationParams`); a `page`
 * param is silently ignored. The list is expected to be small, but the path
 * honours limit/offset so a future "load more" is a call-site change only.
 */

import { useQuery } from '@tanstack/react-query';

import type { Broker } from '../types/admin';
import { authedApiRequest } from '../authedClient';
import type { PaginatedResponse } from './useBookings';

export interface BrokersFilters {
  limit?: number;
  offset?: number;
}

export function brokersQueryKey(filters: BrokersFilters = {}): readonly unknown[] {
  return ['brokers', filters] as const;
}

export function buildBrokersPath(filters: BrokersFilters): string {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  return qs ? `/api/v1/brokers?${qs}` : '/api/v1/brokers';
}

export function useBrokers(options?: { enabled?: boolean; filters?: BrokersFilters }) {
  const filters = options?.filters ?? {};
  return useQuery({
    queryKey: brokersQueryKey(filters),
    queryFn: () => authedApiRequest<PaginatedResponse<Broker>>(buildBrokersPath(filters)),
    enabled: options?.enabled ?? true,
  });
}
