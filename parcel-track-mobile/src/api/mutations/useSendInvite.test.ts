/**
 * Wiring test for the send-invite mutation. Stub the React Query hooks so the
 * hook hands back its options object, then probe `mutationFn` (path/method/body)
 * and `onSuccess` (invalidation). Critically, assert there is **no**
 * Idempotency-Key header — sending an invite is not a financial create.
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import type { InviteCreate } from '../types/admin';
import { useSendInvite } from './useSendInvite';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

const body: InviteCreate = { email: 'agent@example.com', role: 'uk_agent' };

describe('useSendInvite', () => {
  beforeEach(() => jest.clearAllMocks());

  it('POSTs /api/v1/auth/invite with the body and NO Idempotency-Key header', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useSendInvite() as any;
    await mutation.mutationFn(body);

    expect(mockAuthedApiRequest).toHaveBeenCalledWith('/api/v1/auth/invite', {
      method: 'POST',
      body,
    });
    // No idempotency on this endpoint — the options object carries no headers.
    const [, options] = mockAuthedApiRequest.mock.calls[0];
    expect(options).not.toHaveProperty('headers');
  });

  it('invalidates the invites prefix on success', () => {
    const mutation = useSendInvite() as any;
    mutation.onSuccess();

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['invites'] });
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
  });
});
