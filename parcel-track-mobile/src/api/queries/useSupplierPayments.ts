/**
 * Supplier-payments list query for an invoice.
 *
 * GET /api/v1/invoices/{invoiceId}/supplier-payments
 * Auth: **require_admin** — non-admins get a 403 (unlike customer payments,
 * which allow masked reads). The caller passes `enabled: isAdmin` so a
 * non-admin screen never fires the doomed request in the first place.
 *
 * Returns `PaginatedResponse<SupplierPayment>`. No aggregate endpoint exists —
 * callers sum the list client-side (via `sumDecimalStrings`) against the
 * invoice `value` from the booking detail.
 *
 * Query-key convention: resource name first, then the id that scopes the
 * collection. `['supplier-payments', invoiceId]`.
 */

import { useQuery } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { PaginatedResponse } from './useBookings';
import type { SupplierPayment } from '../types/supplierPayment';

export function supplierPaymentsQueryKey(invoiceId: string): readonly unknown[] {
  return ['supplier-payments', invoiceId] as const;
}

export function useSupplierPayments(invoiceId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: supplierPaymentsQueryKey(invoiceId),
    queryFn: () =>
      authedApiRequest<PaginatedResponse<SupplierPayment>>(
        `/api/v1/invoices/${invoiceId}/supplier-payments`,
      ),
    // Gate on the caller's flag AND a present id. Default true so an omitted
    // option behaves like the other list hooks, but supplier-payments callers
    // always pass `enabled: isAdmin` (the endpoint 403s non-admins).
    enabled: !!invoiceId && (options?.enabled ?? true),
  });
}
