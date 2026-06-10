/**
 * Send an invite (Admin → People).
 *
 * POST /api/v1/auth/invite → sends an invite email. Reuses the existing
 * invite-write path (there is no new send endpoint) — note it lives under the
 * `/auth` router prefix, NOT the bare `/invite` the plan assumed. Auth:
 * `require_admin`. **No Idempotency-Key** — that header is only for the three
 * financial creates; an invite send is not a financial side effect. Do not add
 * one.
 *
 * onSuccess invalidates the `['invites']` prefix so the pending-invites list
 * refetches and the new invite appears.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { InviteCreate } from '../types/admin';

export function useSendInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: InviteCreate) =>
      authedApiRequest<{ message: string }>('/api/v1/auth/invite', { method: 'POST', body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invites'] });
    },
  });
}
