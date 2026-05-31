/**
 * Customer-payments aggregate query for a container.
 *
 * GET /api/v1/bookings/{id}/containers/{cid}/customer-payments/aggregate
 * Auth: require_booking_member. Returns rolled-up totals across all tranches:
 * `{ total_received, total_variance, total_expenses, total_banked, tranche_count }`.
 *
 * The key is the list key (`customerPaymentsQueryKey`) plus a trailing
 * `'aggregate'`, so a single `invalidateQueries({ queryKey: ['customer-
 * payments', bookingId, containerId] })` (a prefix) refetches both. See the
 * create mutation.
 */

import { useQuery } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { CustomerPaymentAggregate } from '../types/payment';
import { customerPaymentsQueryKey } from './useCustomerPayments';

export function customerPaymentAggregateQueryKey(
  bookingId: string,
  containerId: string,
): readonly unknown[] {
  return [...customerPaymentsQueryKey(bookingId, containerId), 'aggregate'] as const;
}

export function useCustomerPaymentAggregate(bookingId: string, containerId: string) {
  return useQuery({
    queryKey: customerPaymentAggregateQueryKey(bookingId, containerId),
    queryFn: () =>
      authedApiRequest<CustomerPaymentAggregate>(
        `/api/v1/bookings/${bookingId}/containers/${containerId}/customer-payments/aggregate`,
      ),
    enabled: !!bookingId && !!containerId,
  });
}
