/**
 * Wiring test for the supplier-payment create mutation (mirror of the
 * customer-payment one). Stub the React Query hooks so calling the hook hands
 * back its options object, then probe `mutationFn` (path + method + body +
 * Idempotency-Key header) and `onSuccess` (both invalidations).
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import type { SupplierPaymentCreate } from '../types/supplierPayment';
import { useCreateSupplierPayment } from './useCreateSupplierPayment';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

const body: SupplierPaymentCreate = {
  swift_ref: 'SWIFT-123',
  payment_date: '2026-06-01',
  amount: '8000.00',
  currency: 'USD',
  payment_type: 'partial',
};

describe('useCreateSupplierPayment', () => {
  beforeEach(() => jest.clearAllMocks());

  it('POSTs the invoice-scoped path with the body and the Idempotency-Key header', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useCreateSupplierPayment('inv-1', 'b-1') as any;
    await mutation.mutationFn({ body, idempotencyKey: 'idem-123' });

    expect(mockAuthedApiRequest).toHaveBeenCalledWith('/api/v1/invoices/inv-1/supplier-payments', {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': 'idem-123' },
    });
  });

  it('invalidates both the supplier-payments key and the parent booking key on success', () => {
    const mutation = useCreateSupplierPayment('inv-1', 'b-1') as any;
    mutation.onSuccess();

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['supplier-payments', 'inv-1'],
    });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['booking', 'b-1'] });
    expect(invalidateQueries).toHaveBeenCalledTimes(2);
  });
});
