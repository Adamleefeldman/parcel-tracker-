/**
 * Record a supplier payment (outbound USD wire) against an invoice.
 *
 * POST /api/v1/invoices/{invoiceId}/supplier-payments
 * Auth: require_admin. Requires an `Idempotency-Key` header (missing → 400);
 * the server caches the response 24h, so resubmitting with the SAME key after
 * a lost response returns the cached `SupplierPaymentOut` instead of creating
 * a second payment. The caller generates one key per form mount and passes it
 * here (see the record-supplier-payment form) — never regenerate per tap.
 *
 * Status is **server-set** to `confirmed` on creation — the client never sends
 * a status and there is no separate confirm step. One POST is final.
 *
 * onSuccess invalidates two keys:
 *   - `['supplier-payments', invoiceId]` — refetch this invoice's list +
 *     re-derive the "Paid X / Y" progress.
 *   - `['booking', bookingId]` — recording a payment that crosses the
 *     cumulative-paid threshold auto-advances the booking to
 *     `payment_confirmed` server-side; refetching surfaces the new status pill.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { bookingQueryKey } from '../queries/useBooking';
import { supplierPaymentsQueryKey } from '../queries/useSupplierPayments';
import { authedApiRequest } from '../authedClient';
import type { SupplierPayment, SupplierPaymentCreate } from '../types/supplierPayment';

export interface CreateSupplierPaymentVars {
  body: SupplierPaymentCreate;
  idempotencyKey: string;
}

export function useCreateSupplierPayment(invoiceId: string, bookingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ body, idempotencyKey }: CreateSupplierPaymentVars) =>
      authedApiRequest<SupplierPayment>(`/api/v1/invoices/${invoiceId}/supplier-payments`, {
        method: 'POST',
        body,
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: supplierPaymentsQueryKey(invoiceId) });
      queryClient.invalidateQueries({ queryKey: bookingQueryKey(bookingId) });
    },
  });
}
