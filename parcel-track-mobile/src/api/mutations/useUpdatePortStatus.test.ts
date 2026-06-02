/**
 * Mutation-wiring tests. These hooks can't be rendered under the node-env
 * jest config (no React renderer), so we mock the two React Query hooks they
 * call: `useMutation` returns the options object it's given (letting us probe
 * `mutationFn` + `onSuccess`), and `useQueryClient` returns a stub with a
 * spy-able `invalidateQueries`. We assert the path/method/body the mutationFn
 * builds and that onSuccess invalidates the parent booking key.
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import { useUpdatePortStatus } from './useUpdatePortStatus';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

describe('useUpdatePortStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('PATCHes the port-status path with the given body', async () => {
    mockAuthedApiRequest.mockResolvedValue({ message: 'Container status updated' });

    const mutation = useUpdatePortStatus('booking-1', 'container-9') as any;
    await mutation.mutationFn({
      port_status: 'released',
      destin8_ref: 'D8-123',
      notes: 'cleared customs',
    });

    expect(mockAuthedApiRequest).toHaveBeenCalledWith(
      '/api/v1/bookings/booking-1/containers/container-9/port-status',
      {
        method: 'PATCH',
        body: { port_status: 'released', destin8_ref: 'D8-123', notes: 'cleared customs' },
      },
    );
  });

  it('invalidates the parent ["booking", bookingId] key on success', () => {
    const mutation = useUpdatePortStatus('booking-1', 'container-9') as any;
    mutation.onSuccess();

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['booking', 'booking-1'] });
  });
});
