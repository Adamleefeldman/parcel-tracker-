/**
 * Update a container's port status / Destin8 ref / notes.
 *
 * PATCH /api/v1/bookings/{id}/containers/{cid}/port-status
 * Auth: require_booking_member (any non-customer member of the booking).
 * Body: ContainerStatusUpdate — all fields optional.
 * Response: { message } — does NOT return the updated container, which is why
 * we invalidate-and-refetch rather than write the result into the cache.
 *
 * See `src/api/mutations` convention: every container mutation invalidates the
 * parent `['booking', bookingId]` key, because Phase 2's `useContainer` reads
 * the container out of the booking-detail response (no standalone container
 * endpoint). Caller wires onSuccess/onError for toast + navigation.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { bookingQueryKey } from '../queries/useBooking';
import { authedApiRequest } from '../authedClient';
import type { PortStatus } from '../types/enums';

export interface PortStatusUpdateBody {
  port_status?: PortStatus;
  destin8_ref?: string;
  notes?: string;
}

export function useUpdatePortStatus(bookingId: string, containerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PortStatusUpdateBody) =>
      authedApiRequest<{ message: string }>(
        `/api/v1/bookings/${bookingId}/containers/${containerId}/port-status`,
        { method: 'PATCH', body },
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: bookingQueryKey(bookingId) }),
  });
}
