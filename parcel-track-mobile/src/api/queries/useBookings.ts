/**
 * Bookings list query.
 *
 * Query-key convention for this codebase: arrays starting with the resource
 * name, then a stable-keyed object of filters. Future hooks should follow
 * the same shape so cache invalidation has obvious targets:
 *
 *   ['bookings', { status, date_from, date_to, page }]
 *   ['bookings', id]
 *   ['containers', { booking_id }]
 *
 * Pagination/filters are not exposed yet — defaults are fine until volume
 * makes them necessary. When they land, extend `BookingsFilters` and pass
 * the values through here without changing call sites that omit them.
 */

import { useQuery } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';

export interface Booking {
  id: string;
  reference: string;
  booking_number: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  total: number;
  items: T[];
}

export interface BookingsFilters {
  status?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
}

export function bookingsQueryKey(filters: BookingsFilters = {}): readonly unknown[] {
  return ['bookings', filters] as const;
}

export function useBookings(filters: BookingsFilters = {}) {
  return useQuery({
    queryKey: bookingsQueryKey(filters),
    queryFn: () => authedApiRequest<PaginatedResponse<Booking>>(buildPath(filters)),
  });
}

function buildPath(filters: BookingsFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.page !== undefined) params.set('page', String(filters.page));
  const qs = params.toString();
  return qs ? `/api/v1/bookings?${qs}` : '/api/v1/bookings';
}
