/**
 * Wiring tests for the two dispute mutation hooks. Same mocking strategy as
 * `useUpdatePortStatus.test.ts`: stub the React Query hooks so calling the
 * hook hands back the options object, then probe mutationFn + onSuccess.
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import { useAcknowledgeDispute } from './useAcknowledgeDispute';
import { useOpenDispute } from './useOpenDispute';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

describe('useOpenDispute', () => {
  beforeEach(() => jest.clearAllMocks());

  it('PATCHes the dispute path with the reason body', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useOpenDispute('b-1', 'c-2') as any;
    await mutation.mutationFn({ reason: 'short shipment' });

    expect(mockAuthedApiRequest).toHaveBeenCalledWith(
      '/api/v1/bookings/b-1/containers/c-2/dispute',
      { method: 'PATCH', body: { reason: 'short shipment' } },
    );
  });

  it('invalidates the parent booking key on success', () => {
    const mutation = useOpenDispute('b-1', 'c-2') as any;
    mutation.onSuccess();
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['booking', 'b-1'] });
  });
});

describe('useAcknowledgeDispute', () => {
  beforeEach(() => jest.clearAllMocks());

  it('PATCHes the acknowledge path with an empty body', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useAcknowledgeDispute('b-1', 'c-2') as any;
    await mutation.mutationFn();

    expect(mockAuthedApiRequest).toHaveBeenCalledWith(
      '/api/v1/bookings/b-1/containers/c-2/dispute/acknowledge',
      { method: 'PATCH', body: {} },
    );
  });

  it('invalidates the parent booking key on success', () => {
    const mutation = useAcknowledgeDispute('b-1', 'c-2') as any;
    mutation.onSuccess();
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['booking', 'b-1'] });
  });
});
