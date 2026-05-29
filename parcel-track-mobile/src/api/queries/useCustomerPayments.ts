/**
 * Customer-payments list query for a container.
 *
 * GET /api/v1/bookings/{id}/containers/{cid}/customer-payments
 * Auth: require_booking_member. Returns `PaginatedResponse<CustomerPayment>`,
 * ordered by tranche_index then created_at. Financial fields are masked
 * (null) for non-admins — the UI renders those as "—".
 *
 * Query-key convention: resource name first, then the ids that scope the
 * collection. The aggregate hook's key (`useCustomerPaymentAggregate`) is this
 * key plus a trailing `'aggregate'`, so invalidating THIS key (a prefix)
 * refetches both the list and the aggregate in one call — see the create
 * mutation's onSuccess.
 */

import { useQuery } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { PaginatedResponse } from './useBookings';
import type { CustomerPayment } from '../types/payment';

export function customerPaymentsQueryKey(
  bookingId: string,
  containerId: string,
): readonly unknown[] {
  return ['customer-payments', bookingId, containerId] as const;
}

export function useCustomerPayments(bookingId: string, containerId: string) {
  return useQuery({
    queryKey: customerPaymentsQueryKey(bookingId, containerId),
    queryFn: () =>
      authedApiRequest<PaginatedResponse<CustomerPayment>>(
        `/api/v1/bookings/${bookingId}/containers/${containerId}/customer-payments`,
      ),
    enabled: !!bookingId && !!containerId,
  });
}
