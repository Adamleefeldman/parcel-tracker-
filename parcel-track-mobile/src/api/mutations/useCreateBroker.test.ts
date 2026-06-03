/**
 * Wiring test for the create-broker mutation. Stub the React Query hooks so the
 * hook hands back its options object, then probe `mutationFn` (path/method/body)
 * and `onSuccess` (invalidation). Critically, assert there is **no**
 * Idempotency-Key header — it's only for the financial creates.
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import type { BrokerCreate } from '../types/admin';
import { useCreateBroker } from './useCreateBroker';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

const body: BrokerCreate = { code: 'BRK-UK-01', name: 'Acme Brokers', phone: '+44 20 1234' };

describe('useCreateBroker', () => {
  beforeEach(() => jest.clearAllMocks());

  it('POSTs /api/v1/brokers with the body and NO Idempotency-Key header', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useCreateBroker() as any;
    await mutation.mutationFn(body);

    expect(mockAuthedApiRequest).toHaveBeenCalledWith('/api/v1/brokers', {
      method: 'POST',
      body,
    });
    // No idempotency on this endpoint — the options object carries no headers.
    const [, options] = mockAuthedApiRequest.mock.calls[0];
    expect(options).not.toHaveProperty('headers');
  });

  it('invalidates the brokers prefix on success', () => {
    const mutation = useCreateBroker() as any;
    mutation.onSuccess();

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['brokers'] });
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
  });
});
