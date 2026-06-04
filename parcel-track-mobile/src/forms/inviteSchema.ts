/**
 * Validation schema for the send-invite form (react-hook-form + zod).
 *
 * Mirrors the backend's `InviteRequest` single-field rules: a valid `email` and
 * a `role` ∈ UserRole. The Admin console sends org-level invites, so
 * `booking_id` is never collected.
 *
 * zod gotcha (TS 5.5+): a `.refine((v) => v === 'a' || …)` predicate is inferred
 * as a type guard and narrows the field's type to the union, which then rejects
 * the `''` default. Use the `.includes(v)` form so `role` stays a plain
 * `string` (so the blank default validates as "not chosen yet").
 */

import { z } from 'zod';

import type { InviteCreate } from '../api/types/admin';
import { USER_ROLES, type UserRole } from '../api/types/enums';

const ROLE_VALUES: readonly string[] = USER_ROLES;

export const inviteSchema = z.object({
  email: z.string().trim().min(1, 'Email is required').email('Enter a valid email'),
  role: z.string().refine((v) => ROLE_VALUES.includes(v), 'Select a role'),
});

/** All-string form values (RHF state). Mapped to the body via `toCreateBody`. */
export type InviteFormValues = z.infer<typeof inviteSchema>;

export const defaultInviteFormValues: InviteFormValues = {
  email: '',
  role: '',
};

/**
 * Map validated values to the request body. Trims + lowercases the email (the
 * backend normalises identically); `booking_id` is omitted (org-level invite).
 */
export function toCreateBody(values: InviteFormValues): InviteCreate {
  return {
    email: values.email.trim().toLowerCase(),
    role: values.role as UserRole,
  };
}
