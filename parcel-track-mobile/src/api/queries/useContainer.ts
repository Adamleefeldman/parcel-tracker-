/**
 * Container detail "query" — actually a derived read off the parent booking.
 *
 * The backend has no standalone `GET /api/v1/containers/{id}` endpoint: every
 * container is reachable only as a nested object inside `BookingDetail`. So
 * `useContainer` runs `useBooking(bookingId)` and walks the result for the
 * matching container, mirroring the React Query loading/error shape so the
 * detail screen can treat it like any other query.
 *
 * Containers can appear under both `bill_of_lading.containers` and
 * `delivery_points[].containers`; the same id can show up in both lists.
 * `findContainerInBooking` de-dupes by returning the first hit.
 *
 * When the backend grows a real `/containers/{id}` endpoint, swap the body
 * of this hook for a direct fetch and drop the helper — call sites stay the
 * same.
 */

import type { BookingDetail } from '../types/booking';
import type { Container } from '../types/container';
import { useBooking } from './useBooking';

export function findContainerInBooking(
  booking: BookingDetail | undefined,
  containerId: string | undefined,
): Container | undefined {
  if (!booking || !containerId) return undefined;
  const fromBL = booking.bill_of_lading?.containers ?? [];
  for (const c of fromBL) {
    if (c.id === containerId) return c;
  }
  for (const dp of booking.delivery_points) {
    for (const c of dp.containers) {
      if (c.id === containerId) return c;
    }
  }
  return undefined;
}

export function useContainer(bookingId: string, containerId: string) {
  const bookingQuery = useBooking(bookingId);
  const data = findContainerInBooking(bookingQuery.data, containerId);
  return {
    data,
    isLoading: bookingQuery.isLoading,
    isError: bookingQuery.isError,
    error: bookingQuery.error,
    isRefetching: bookingQuery.isRefetching,
    refetch: bookingQuery.refetch,
  };
}
