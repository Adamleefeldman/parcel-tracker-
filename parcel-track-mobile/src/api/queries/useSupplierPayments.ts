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
 * invoice `value` from the booking detail. Because that client-side sum is a
 * **financial** total, a silently-truncated list would silently under-count it.
 * So we request a high `limit` (well above any realistic per-invoice payment
 * count) to fetch the whole list in one page, and the caller still compares
 * `total` vs the fetched count and shows a "partial" marker if they ever differ
 * — the sum is never silently wrong. (`total` always reflects the full count
 * regardless of `limit`.)
 *
 * Query-key convention: resource name first, then the id that scopes the
 * collection. `['supplier-payments', invoiceId]`.
 */

import { useQuery } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { PaginatedResponse } from './useBookings';
import type { SupplierPayment } from '../types/supplierPayment';

/**
 * Page size for the supplier-payments fetch. High enough to capture every
 * payment on any real invoice in one request so the client-side total is exact.
 * The backend caps at this; if `total` ever exceeds it the UI flags the sum as
 * partial rather than mislead.
 */
export const SUPPLIER_PAYMENTS_PAGE_LIMIT = 500;

export function supplierPaymentsQueryKey(invoiceId: string): readonly unknown[] {
  return ['supplier-payments', invoiceId] as const;
}

export function useSupplierPayments(invoiceId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: supplierPaymentsQueryKey(invoiceId),
    queryFn: () =>
      authedApiRequest<PaginatedResponse<SupplierPayment>>(
        `/api/v1/invoices/${invoiceId}/supplier-payments?limit=${SUPPLIER_PAYMENTS_PAGE_LIMIT}`,
      ),
    // Gate on the caller's flag AND a present id. Default true so an omitted
    // option behaves like the other list hooks, but supplier-payments callers
    // always pass `enabled: isAdmin` (the endpoint 403s non-admins).
    enabled: !!invoiceId && (options?.enabled ?? true),
  });
}
