import type { ContainerLifecycleStatus, ContainerStatus, PortStatus } from './enums';

export interface Broker {
  id: string;
  code: string;
  name: string;
  phone: string | null;
}

export interface Company {
  id: string;
  legal_name: string;
  aliases: string[] | null;
  registration_no: string | null;
  vat_no: string | null;
  default_address: string | null;
}

/**
 * Mirrors `ContainerOut` (`app/schemas/schemas.py:399`). Container has three
 * separate status fields — see the enums file for what each one means.
 *
 * Financial fields (`sale_price_*`) are nulled by the backend for non-admin
 * users; render them defensively (treat null as "not visible to me").
 */
export interface Container {
  id: string;
  container_number: string;
  seal_number: string | null;
  port_status: PortStatus;
  status: ContainerStatus;
  lifecycle_status: ContainerLifecycleStatus;
  destin8_ref: string | null;
  notes: string | null;
  delivery_type: 'direct' | 'via_warehouse' | null;
  broker: Broker | null;
  end_company: Company | null;
  sale_price_per_tray: string | null;
  sale_price_per_pallet: string | null;
  sale_price_total: string | null;
  sale_currency: string;
  dispute_reason: string | null;
  disputed_at: string | null;
  dispute_acknowledged_at: string | null;
  dispute_acknowledged_by: string | null;
  updated_at: string;
}
