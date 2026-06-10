/**
 * Users list query (Admin → People).
 *
 * GET /api/v1/users → PaginatedResponse<UserAdmin>. Auth: `require_admin`, so
 * callers pass `enabled: isAdmin` — a deep-linked non-admin never fires the
 * doomed 403 request. The user base is tiny, so the screen fetches one capped
 * page (`limit: 200`) and computes the role/active summary client-side.
 *
 * Key shape follows the codebase convention: resource name + stable filters
 * object. Pagination uses `limit`/`offset` (a `page` param is silently ignored).
 */

import { useQuery } from '@tanstack/react-query';

import type { UserAdmin } from '../types/admin';
import { authedApiRequest } from '../authedClient';
import type { PaginatedResponse } from './useBookings';

export interface UsersFilters {
  limit?: number;
  offset?: number;
}

export function usersQueryKey(filters: UsersFilters = {}): readonly unknown[] {
  return ['users', filters] as const;
}

export function buildUsersPath(filters: UsersFilters): string {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  return qs ? `/api/v1/users?${qs}` : '/api/v1/users';
}

export function useUsers(options?: { enabled?: boolean; filters?: UsersFilters }) {
  const filters = options?.filters ?? {};
  return useQuery({
    queryKey: usersQueryKey(filters),
    queryFn: () => authedApiRequest<PaginatedResponse<UserAdmin>>(buildUsersPath(filters)),
    enabled: options?.enabled ?? true,
  });
}
