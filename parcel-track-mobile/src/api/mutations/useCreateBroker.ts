/**
 * Create a broker (admin "Operations").
 *
 * POST /api/v1/brokers → Broker. Auth: `require_admin`. **No Idempotency-Key** —
 * that header is only required on the three financial creates (customer/supplier
 * payment, invoice); a broker create is not a financial side effect. Do not add
 * one (the server doesn't expect it here).
 *
 * onSuccess invalidates the `['brokers']` prefix so every brokers-list slot
 * refetches and the new row appears.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { Broker, BrokerCreate } from '../types/admin';

export function useCreateBroker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BrokerCreate) =>
      authedApiRequest<Broker>('/api/v1/brokers', { method: 'POST', body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brokers'] });
    },
  });
}
