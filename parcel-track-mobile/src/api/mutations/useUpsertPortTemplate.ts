/**
 * Upsert a port template (admin "Operations").
 *
 * PUT /api/v1/port-templates/{port} → PortTemplate. Auth: `require_admin`. The
 * one row per UK port is created-or-updated by this single PUT (there is no
 * separate create vs edit; ports are a fixed enum). **No Idempotency-Key** — PUT
 * is idempotent by nature, and the header is only for the financial creates.
 *
 * Variables carry `{ port, body }`. onSuccess invalidates `['port-templates']`
 * so the list re-renders the saved free-days + rates.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import type { UKPort } from '../types/enums';
import { authedApiRequest } from '../authedClient';
import type { PortTemplate, PortTemplateUpsert } from '../types/admin';

export interface UpsertPortTemplateVars {
  port: UKPort;
  body: PortTemplateUpsert;
}

export function useUpsertPortTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ port, body }: UpsertPortTemplateVars) =>
      authedApiRequest<PortTemplate>(`/api/v1/port-templates/${port}`, { method: 'PUT', body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['port-templates'] });
    },
  });
}
