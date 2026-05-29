/**
 * Acknowledge an open dispute on a container.
 *
 * PATCH /api/v1/bookings/{id}/containers/{cid}/dispute/acknowledge
 * Auth: require_admin. Body: {} (empty — extension point for an ack note).
 * Response: full ContainerOut. Preserves dispute history; clears the parent
 * booking's completion blocker.
 *
 * Like `useOpenDispute`, the response carries the updated container — a future
 * optimisation could `setQueryData` it in. For now: invalidate-and-refetch.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { bookingQueryKey } from '../queries/useBooking';
import { authedApiRequest } from '../authedClient';
import type { Container } from '../types/container';

export function useAcknowledgeDispute(bookingId: string, containerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      authedApiRequest<Container>(
        `/api/v1/bookings/${bookingId}/containers/${containerId}/dispute/acknowledge`,
        { method: 'PATCH', body: {} },
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: bookingQueryKey(bookingId) }),
  });
}
