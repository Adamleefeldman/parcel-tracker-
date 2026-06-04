/**
 * Hand-typed mirrors of the admin "Operations" backend schemas — brokers,
 * end customers (companies), and per-port templates. Source of truth:
 * `parcel-track/app/schemas/schemas.py` (`Broker*`, `Company*`,
 * `PortTemplate*`) + `app/api/routes/{parties,port_templates}.py`.
 *
 * **Auth:** list (GET) is any authenticated user; create/upsert is
 * `require_admin`. The client gates the read queries `enabled: isAdmin` anyway
 * (defense-in-depth + no doomed request for a deep-linked non-admin).
 *
 * **Money discipline:** the port-template rate fields are backend `Decimal`s,
 * serialised to JSON **strings** under `response_model`. Keep them `string`
 * end-to-end — display via `formatMoney`, never `parseFloat` (see AGENTS.md →
 * Money). Free-days are plain integer counts (`number`).
 *
 * **No edit/delete:** the backend exposes create + read only for brokers and
 * companies (no PATCH/DELETE), and upsert-only for port templates (no DELETE) —
 * so there are no `*Update` shapes here.
 */

import type { UKPort, UserRole } from './enums';

// ── People (users + invites) ──────────────────────────────────────────────────
//
// Admin-only read views backing the Admin tab's PEOPLE section, plus the
// send-invite body. Source of truth: `parcel-track/app/api/routes/admin.py` +
// `app/schemas/schemas.py` (`UserOut`/`InviteOut`/`AuditLogOut`/`InviteRequest`).
// View + send-invites scope only — no revoke/deactivate/role-change shapes.

/**
 * A user as seen by an admin. The backend reuses `UserOut` for `GET /users`
 * (no separate UserAdminOut) — sensitive fields (`hashed_password`,
 * `expo_push_token`) are never serialised.
 */
export interface UserAdmin {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

/**
 * An invite token as seen by an admin (`InviteOut`). NEVER carries
 * `token_hash`. `expired` is a backend-derived flag (`expires_at <= now()` and
 * not yet `used`).
 */
export interface Invite {
  id: string;
  email: string;
  role: UserRole;
  expires_at: string;
  created_at: string;
  used: boolean;
  expired: boolean;
}

/**
 * A single audit-log entry (`AuditLogOut`), newest-first in the feed.
 * `old_value`/`new_value` are stored JSON **strings** (or null) — pretty-print
 * them defensively (they may be null or non-JSON). `actor_name` is joined from
 * `User` server-side.
 */
export interface AuditLogEntry {
  id: string;
  created_at: string;
  actor_id: string;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  old_value: string | null;
  new_value: string | null;
  ip_address: string | null;
  booking_id: string | null;
}

/**
 * Body for `POST /api/v1/invite` (`InviteRequest`). The Admin console sends
 * org-level invites, so `booking_id` is omitted. NO Idempotency-Key (not a
 * financial create).
 */
export interface InviteCreate {
  email: string;
  role: UserRole;
}

// ── Brokers ───────────────────────────────────────────────────────────────────

export interface Broker {
  id: string;
  code: string;
  name: string;
  phone: string | null;
}

export interface BrokerCreate {
  code: string;
  name: string;
  phone?: string;
}

// ── End customers (companies) ─────────────────────────────────────────────────

export interface Company {
  id: string;
  legal_name: string;
  aliases: string[] | null;
  registration_no: string | null;
  vat_no: string | null;
  default_address: string | null;
}

export interface CompanyCreate {
  legal_name: string;
  aliases?: string[];
  registration_no?: string;
  vat_no?: string;
  default_address?: string;
}

// ── Port templates ────────────────────────────────────────────────────────────

export interface PortTemplate {
  id: string;
  port: UKPort;
  free_days_detention: number;
  free_days_demurrage: number;
  /** Decimal → JSON string. Keep as string; format via `formatMoney`. */
  detention_rate_gbp_after: string | null;
  demurrage_rate_gbp_after: string | null;
  created_at: string;
  updated_at: string;
}

/** PUT body for `/port-templates/{port}` (upsert). Free-days required (≥0);
 * rates optional decimal strings (≥0, omitted when blank). */
export interface PortTemplateUpsert {
  free_days_detention: number;
  free_days_demurrage: number;
  detention_rate_gbp_after?: string;
  demurrage_rate_gbp_after?: string;
}
