/**
 * Cosmetic, client-side role checks.
 *
 * These decide which action buttons a screen *shows* — nothing more. The
 * server is the real authority: the dispute endpoints are `require_admin`
 * and the port-status endpoint is `require_booking_member`, so a non-admin
 * who somehow reaches an admin endpoint gets a 403 regardless of what the UI
 * rendered. NEVER treat a hidden button as a security boundary.
 *
 * Role comes from the decoded JWT (`useAuth().user?.role`), itself a UI hint
 * (see `src/auth/jwt.ts`). All helpers are null-safe: an undefined role —
 * anonymous, or a token we couldn't decode — denies, the restrictive default.
 */

import type { UserRole } from '../api/types/enums';

/** Admin-only: open and acknowledge container disputes. */
export const canManageDisputes = (role?: UserRole): boolean => role === 'admin';

/**
 * Any booking member who isn't a customer can update a container's port
 * status. The backend gates this with `require_booking_member`; since viewing
 * the container already implies membership, the practical UI rule is
 * "non-customer".
 */
export const canUpdatePortStatus = (role?: UserRole): boolean =>
  role === 'admin' || role === 'morocco_agent' || role === 'uk_agent';
