/**
 * Wiring test for the port-template upsert mutation. Probes that it PUTs the
 * per-port path with the body and no Idempotency-Key, and invalidates the
 * single-slot `['port-templates']` key on success.
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import type { PortTemplateUpsert } from '../types/admin';
import { useUpsertPortTemplate } from './useUpsertPortTemplate';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

const body: PortTemplateUpsert = {
  free_days_detention: 5,
  free_days_demurrage: 3,
  detention_rate_gbp_after: '120.00',
};

describe('useUpsertPortTemplate', () => {
  beforeEach(() => jest.clearAllMocks());

  it('PUTs the per-port path with the body and NO Idempotency-Key header', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useUpsertPortTemplate() as any;
    await mutation.mutationFn({ port: 'felixstowe', body });

    expect(mockAuthedApiRequest).toHaveBeenCalledWith('/api/v1/port-templates/felixstowe', {
      method: 'PUT',
      body,
    });
    const [, options] = mockAuthedApiRequest.mock.calls[0];
    expect(options).not.toHaveProperty('headers');
  });

  it('invalidates the port-templates key on success', () => {
    const mutation = useUpsertPortTemplate() as any;
    mutation.onSuccess();

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['port-templates'] });
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
  });
});
