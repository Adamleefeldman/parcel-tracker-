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

import type { UKPort } from './enums';

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
