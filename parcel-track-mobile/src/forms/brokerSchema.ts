/**
 * Validation schema for the create-broker form (react-hook-form + zod).
 *
 * A broker is three fields (`code`, `name`, `phone?`) — at the ≤3-field
 * threshold a hand-rolled `useState` form would be acceptable (see AGENTS.md →
 * Forms), but a small zod schema keeps the create forms uniform and gives the
 * same `formState.isValid` submit-gating the other modal forms use.
 *
 * Mirrors the backend's single-field rules only (`BrokerCreate`): `code` + `name`
 * required (non-empty), `phone` optional.
 */

import { z } from 'zod';

import type { BrokerCreate } from '../api/types/admin';

export const brokerSchema = z.object({
  code: z.string().trim().min(1, 'Code is required').max(50, 'Too long (max 50)'),
  name: z.string().trim().min(1, 'Name is required').max(200, 'Too long (max 200)'),
  phone: z.string().max(50, 'Too long (max 50)'),
});

/** All-string form values (RHF state). Mapped to the body via `toCreateBody`. */
export type BrokerFormValues = z.infer<typeof brokerSchema>;

export const defaultBrokerFormValues: BrokerFormValues = {
  code: '',
  name: '',
  phone: '',
};

/** Map validated values to the request body. Trims; omits a blank phone. */
export function toCreateBody(values: BrokerFormValues): BrokerCreate {
  const phone = values.phone.trim();
  return {
    code: values.code.trim(),
    name: values.name.trim(),
    ...(phone === '' ? {} : { phone }),
  };
}
