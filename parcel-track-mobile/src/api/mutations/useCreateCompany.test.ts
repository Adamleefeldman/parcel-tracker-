/**
 * Wiring test for the create-company (end customer) mutation. Same shape as the
 * broker test — path/method/body, invalidation, and no Idempotency-Key.
 */

const invalidateQueries = jest.fn();

jest.mock('@tanstack/react-query', () => ({
  useMutation: jest.fn((options) => options),
  useQueryClient: jest.fn(() => ({ invalidateQueries })),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import type { CompanyCreate } from '../types/admin';
import { useCreateCompany } from './useCreateCompany';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

const body: CompanyCreate = {
  legal_name: 'Acme Foods Ltd',
  aliases: ['Acme', 'Acme UK'],
  vat_no: 'GB123456789',
};

describe('useCreateCompany', () => {
  beforeEach(() => jest.clearAllMocks());

  it('POSTs /api/v1/companies with the body and NO Idempotency-Key header', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);

    const mutation = useCreateCompany() as any;
    await mutation.mutationFn(body);

    expect(mockAuthedApiRequest).toHaveBeenCalledWith('/api/v1/companies', {
      method: 'POST',
      body,
    });
    const [, options] = mockAuthedApiRequest.mock.calls[0];
    expect(options).not.toHaveProperty('headers');
  });

  it('invalidates the companies prefix on success', () => {
    const mutation = useCreateCompany() as any;
    mutation.onSuccess();

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['companies'] });
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
  });
});
