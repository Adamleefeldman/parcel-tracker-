/**
 * Wiring test for the customer-payment create mutation. Same strategy as the
 * Phase 3 mutation tests: stub the React Query hooks so calling the hook hands
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
import type { CustomerPaymentCreate } from '../types/payment';
import { useCreateCustomerPayment } from './useCreateCustomerPayment';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

const body: CustomerPaymentCreate = {
  payment_date: '2026-04-15',
  method: 'transfer',
  amount_received: '8000.00',
  banked_total: '8000.00',
  tranche_index: 1,
};

describe('useCreateCustomerPayment', () => {
  beforeEach(() => jest.clearAllMocks());

  it('POSTs the customer-payments path with the body and the Idempotency-Key header', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useCreateCustomerPayment('b-1', 'c-2') as any;
    await mutation.mutationFn({ body, idempotencyKey: 'idem-123' });

    expect(mockAuthedApiRequest).toHaveBeenCalledWith(
      '/api/v1/bookings/b-1/containers/c-2/customer-payments',
      { method: 'POST', body, headers: { 'Idempotency-Key': 'idem-123' } },
    );
  });

  it('invalidates both the customer-payments key and the parent booking key on success', () => {
    const mutation = useCreateCustomerPayment('b-1', 'c-2') as any;
    mutation.onSuccess();

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['customer-payments', 'b-1', 'c-2'],
    });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['booking', 'b-1'] });
    expect(invalidateQueries).toHaveBeenCalledTimes(2);
  });
});
