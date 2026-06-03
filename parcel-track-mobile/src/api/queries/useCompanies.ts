/**
 * End customers (companies) list query (admin "Operations").
 *
 * GET /api/v1/companies → PaginatedResponse<Company>. List is open to any
 * authenticated user; the screen is admin-only, so callers pass
 * `enabled: isAdmin`. Same key/pagination convention as `useBrokers`.
 */

import { useQuery } from '@tanstack/react-query';

import type { Company } from '../types/admin';
import { authedApiRequest } from '../authedClient';
import type { PaginatedResponse } from './useBookings';

export interface CompaniesFilters {
  limit?: number;
  offset?: number;
}

export function companiesQueryKey(filters: CompaniesFilters = {}): readonly unknown[] {
  return ['companies', filters] as const;
}

export function buildCompaniesPath(filters: CompaniesFilters): string {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  return qs ? `/api/v1/companies?${qs}` : '/api/v1/companies';
}

export function useCompanies(options?: { enabled?: boolean; filters?: CompaniesFilters }) {
  const filters = options?.filters ?? {};
  return useQuery({
    queryKey: companiesQueryKey(filters),
    queryFn: () => authedApiRequest<PaginatedResponse<Company>>(buildCompaniesPath(filters)),
    enabled: options?.enabled ?? true,
  });
}
