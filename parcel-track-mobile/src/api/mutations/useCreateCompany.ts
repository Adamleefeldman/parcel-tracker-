/**
 * Create an end customer (company) (admin "Operations").
 *
 * POST /api/v1/companies → Company. Auth: `require_admin`. **No Idempotency-Key**
 * (see `useCreateBroker`). onSuccess invalidates the `['companies']` prefix.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { Company, CompanyCreate } from '../types/admin';

export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CompanyCreate) =>
      authedApiRequest<Company>('/api/v1/companies', { method: 'POST', body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}
