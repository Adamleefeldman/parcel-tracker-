/**
 * Record a customer payment tranche for a container.
 *
 * POST /api/v1/bookings/{id}/containers/{cid}/customer-payments
 * Auth: require_admin. Requires an `Idempotency-Key` header (missing → 400);
 * the server caches the response 24h, so resubmitting with the SAME key after
 * a lost response returns the cached `CustomerPaymentOut` without creating a
 * second tranche. The caller generates one key per form mount and passes it
 * here (see the record-payment form) — never regenerate per tap.
 *
 * onSuccess invalidates two keys:
 *   - `['customer-payments', bookingId, containerId]` — a prefix of the
 *     aggregate key, so the list AND aggregate both refetch in one call.
 *   - `['booking', bookingId]` — the payment recomputes the container's
 *     `lifecycle_status` (→ paid / banked / invoiced), which the container and
 *     booking detail screens read off the booking-detail response.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { bookingQueryKey } from '../queries/useBooking';
import { customerPaymentsQueryKey } from '../queries/useCustomerPayments';
import { authedApiRequest } from '../authedClient';
import type { CustomerPayment, CustomerPaymentCreate } from '../types/payment';

export interface CreateCustomerPaymentVars {
  body: CustomerPaymentCreate;
  idempotencyKey: string;
}

export function useCreateCustomerPayment(bookingId: string, containerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ body, idempotencyKey }: CreateCustomerPaymentVars) =>
      authedApiRequest<CustomerPayment>(
        `/api/v1/bookings/${bookingId}/containers/${containerId}/customer-payments`,
        { method: 'POST', body, headers: { 'Idempotency-Key': idempotencyKey } },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: customerPaymentsQueryKey(bookingId, containerId),
      });
      queryClient.invalidateQueries({ queryKey: bookingQueryKey(bookingId) });
    },
  });
}
