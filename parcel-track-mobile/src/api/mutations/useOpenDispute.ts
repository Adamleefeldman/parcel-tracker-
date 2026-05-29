/**
 * Open a dispute on a container.
 *
 * PATCH /api/v1/bookings/{id}/containers/{cid}/dispute
 * Auth: require_admin. Body: { reason } (required, non-empty server-side).
 * Response: full ContainerOut (lifecycle_status → disputed).
 *
 * The response carries the updated container, so a future optimisation could
 * `queryClient.setQueryData` it in directly (see AGENTS.md → Mutations). For
 * now we use the uniform invalidate-and-refetch of the parent booking.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { bookingQueryKey } from '../queries/useBooking';
import { authedApiRequest } from '../authedClient';
import type { Container } from '../types/container';

export function useOpenDispute(bookingId: string, containerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { reason: string }) =>
      authedApiRequest<Container>(
        `/api/v1/bookings/${bookingId}/containers/${containerId}/dispute`,
        { method: 'PATCH', body },
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: bookingQueryKey(bookingId) }),
  });
}
