/**
 * Wiring test for the mark-notification-read mutation. Same strategy as
 * disputeMutations.test.ts: stub React Query so the hook returns its options
 * object, then probe mutationFn + onSuccess.
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import { useMarkNotificationRead } from './useMarkNotificationRead';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

describe('useMarkNotificationRead', () => {
  beforeEach(() => jest.clearAllMocks());

  it('PATCHes the notification read path', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useMarkNotificationRead() as any;
    await mutation.mutationFn('n-1');

    expect(mockAuthedApiRequest).toHaveBeenCalledWith('/api/v1/notifications/n-1/read', {
      method: 'PATCH',
    });
  });

  it('invalidates the notifications prefix (list + unread-count) on success', () => {
    const mutation = useMarkNotificationRead() as any;
    mutation.onSuccess();
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] });
  });
});
