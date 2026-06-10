/**
 * Invites list query (Admin → People).
 *
 * GET /api/v1/invites?status=pending → PaginatedResponse<Invite>. Auth:
 * `require_admin`; callers pass `enabled: isAdmin`. `token_hash` is never
 * serialised by the backend. `status` ∈ pending|used|expired|all (default
 * `pending` — the only status the Admin console lists).
 *
 * Key shape: `['invites', { status }]`. `useSendInvite` invalidates the bare
 * `['invites']` prefix, which matches every status slot.
 */

import { useQuery } from '@tanstack/react-query';

import type { Invite } from '../types/admin';
import { authedApiRequest } from '../authedClient';
import type { PaginatedResponse } from './useBookings';

export type InviteStatus = 'pending' | 'used' | 'expired' | 'all';

export interface InvitesFilters {
  status?: InviteStatus;
  limit?: number;
  offset?: number;
}

export function invitesQueryKey(filters: InvitesFilters = {}): readonly unknown[] {
  return ['invites', filters] as const;
}

export function buildInvitesPath(filters: InvitesFilters): string {
  const params = new URLSearchParams();
  if (filters.status !== undefined) params.set('status', filters.status);
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  return qs ? `/api/v1/invites?${qs}` : '/api/v1/invites';
}

export function useInvites(options?: { enabled?: boolean; filters?: InvitesFilters }) {
  const filters = options?.filters ?? {};
  return useQuery({
    queryKey: invitesQueryKey(filters),
    queryFn: () => authedApiRequest<PaginatedResponse<Invite>>(buildInvitesPath(filters)),
    enabled: options?.enabled ?? true,
  });
}
