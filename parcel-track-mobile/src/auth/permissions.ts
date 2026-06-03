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

/**
 * Admin-only: record inbound customer payments. The backend's create endpoint
 * is `require_admin` and 403s everyone else regardless of what the UI shows.
 * Non-admin booking members can still *view* the payments section (amounts are
 * masked server-side) — this gate only governs the "Record payment" action.
 */
export const canManageCustomerPayments = (role?: UserRole): boolean => role === 'admin';

/**
 * Admin-only: record outbound supplier payments AND view the list. The
 * backend's create *and* list endpoints are both `require_admin` (non-admins
 * 403 even on read — unlike customer payments, which allow masked reads). The
 * supplier-payments UI uses this both to render the whole section and to gate
 * the list query's `enabled`, so non-admins never fire a doomed 403 request.
 */
export const canManageSupplierPayments = (role?: UserRole): boolean => role === 'admin';

/**
 * Admin-only: the Admin console "Operations" screens (port templates, brokers,
 * end customers). Drives the Admin tab `href` (cosmetic) AND every list query's
 * `enabled` gate, so a non-admin who deep-links an admin URL renders a "not
 * permitted" body and never fires a request. The create/upsert endpoints are
 * `require_admin` server-side regardless — this is defense-in-depth, not the
 * real gate.
 */
export const canManageAdmin = (role?: UserRole): boolean => role === 'admin';
