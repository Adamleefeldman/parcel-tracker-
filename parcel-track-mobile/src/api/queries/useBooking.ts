/**
 * Single-booking detail query. Hits `GET /api/v1/bookings/{id}` and returns
 * the fully-hydrated `BookingDetail` (nested BL, vessel, containers, legs,
 * delivery points, POs, payments).
 *
 * Query-key convention: `['booking', id]` (singular resource + id). Sibling
 * to the `['bookings', filters]` collection key — see useBookings.ts.
 */

import { useQuery } from '@tanstack/react-query';

import type { BookingDetail } from '../types/booking';
import { authedApiRequest } from '../authedClient';

export function bookingQueryKey(id: string): readonly unknown[] {
  return ['booking', id] as const;
}

export function useBooking(id: string) {
  return useQuery({
    queryKey: bookingQueryKey(id),
    queryFn: () => authedApiRequest<BookingDetail>(`/api/v1/bookings/${id}`),
    enabled: !!id,
  });
}
