/**
 * Tests for the supplier-payments list hook. The key builder is asserted
 * directly; for the `enabled` gating we stub `useQuery` so the hook hands back
 * its options object (no React renderer under the node-env jest config), then
 * probe `enabled` and the queryFn's path.
 */

jest.mock('@tanstack/react-query', () => ({
  useQuery: jest.fn((options) => options),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import {
  SUPPLIER_PAYMENTS_PAGE_LIMIT,
  supplierPaymentsQueryKey,
  useSupplierPayments,
} from './useSupplierPayments';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

describe('supplierPaymentsQueryKey', () => {
  it('builds the key as [resource, invoiceId]', () => {
    expect(supplierPaymentsQueryKey('inv-1')).toEqual(['supplier-payments', 'inv-1']);
  });

  it('produces distinct keys for different invoices', () => {
    expect(supplierPaymentsQueryKey('inv-1')).not.toEqual(supplierPaymentsQueryKey('inv-2'));
  });
});

describe('useSupplierPayments', () => {
  beforeEach(() => jest.clearAllMocks());

  it('hits the invoice-scoped path with the backend max limit so the client-side sum is exact', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);
    const query = useSupplierPayments('inv-1', { enabled: true }) as any;
    await query.queryFn();
    // Literal 200, not the constant: the backend's MAX_PAGE_SIZE 422s anything
    // higher, so a drifted constant must fail here, not in production.
    expect(mockAuthedApiRequest).toHaveBeenCalledWith(
      '/api/v1/invoices/inv-1/supplier-payments?limit=200',
    );
  });

  it('keeps the page limit at the backend MAX_PAGE_SIZE cap', () => {
    expect(SUPPLIER_PAYMENTS_PAGE_LIMIT).toBe(200);
  });

  it('is disabled when the caller is not admin (enabled: false)', () => {
    const query = useSupplierPayments('inv-1', { enabled: false }) as any;
    expect(query.enabled).toBe(false);
  });

  it('is enabled when admin and the invoiceId is present', () => {
    const query = useSupplierPayments('inv-1', { enabled: true }) as any;
    expect(query.enabled).toBe(true);
  });

  it('is disabled when the invoiceId is missing even if enabled is passed', () => {
    const query = useSupplierPayments('', { enabled: true }) as any;
    expect(query.enabled).toBe(false);
  });
});
