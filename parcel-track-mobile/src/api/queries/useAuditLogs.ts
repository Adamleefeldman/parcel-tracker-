/**
 * Audit-log feed query (Admin → System).
 *
 * GET /api/v1/audit-logs → PaginatedResponse<AuditLogEntry>, newest first.
 * Auth: `require_admin`; callers pass `enabled: isAdmin`. Global feed with
 * load-more (the screen bumps `limit` to fetch more — the backend supports
 * optional `booking_id`/`actor_id` filters, unused here).
 *
 * Key shape: `['audit-logs', { limit, offset }]` — different windows are
 * distinct cache slots, the resource name first so an invalidate-all is easy.
 */

import { keepPreviousData, useQuery } from '@tanstack/react-query';

import type { AuditLogEntry } from '../types/admin';
import { authedApiRequest } from '../authedClient';
import type { PaginatedResponse } from './useBookings';

export interface AuditLogsFilters {
  limit?: number;
  offset?: number;
}

export function auditLogsQueryKey(filters: AuditLogsFilters = {}): readonly unknown[] {
  return ['audit-logs', filters] as const;
}

export function buildAuditLogsPath(filters: AuditLogsFilters): string {
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  return qs ? `/api/v1/audit-logs?${qs}` : '/api/v1/audit-logs';
}

export function useAuditLogs(options?: { enabled?: boolean; filters?: AuditLogsFilters }) {
  const filters = options?.filters ?? {};
  return useQuery({
    queryKey: auditLogsQueryKey(filters),
    queryFn: () => authedApiRequest<PaginatedResponse<AuditLogEntry>>(buildAuditLogsPath(filters)),
    enabled: options?.enabled ?? true,
    // Load-more grows `limit` (a new cache slot); keep the prior window visible
    // while the larger one loads instead of flashing the full-screen spinner.
    placeholderData: keepPreviousData,
  });
}
