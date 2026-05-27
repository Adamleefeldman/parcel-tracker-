import type { BookingStatus } from './enums';
import type { Broker, Company, Container } from './container';

/**
 * Mirrors `BookingDetailOut` (`app/schemas/schemas.py:113`). Includes every
 * nested relationship — one call hydrates the booking detail screen.
 *
 * Pydantic `Decimal` fields come over the wire as strings. Keep them as
 * `string` here; convert at render time only when needed.
 */

export interface Invoice {
  id: string;
  invoice_number: string;
  invoice_date: string;
  value: string | null;
  currency: string;
  payment_terms: string | null;
  due_date: string | null;
  status: string;
  discrepancy_acknowledged: boolean;
  created_at: string;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  po_date: string;
  product_description: string;
  quantity: string;
  quantity_unit: string;
  total_value: string | null;
  currency: string;
  status: string;
  notes: string | null;
  invoice: Invoice | null;
  created_at: string;
}

export interface SupplierPayment {
  id: string;
  swift_ref: string | null;
  payment_date: string;
  amount: string | null;
  currency: string;
  payment_type: string;
  status: string;
  created_at: string;
}

export interface VesselUpdate {
  id: string;
  status: string;
  current_position_note: string | null;
  revised_eta: string | null;
  source: string;
  created_at: string;
}

export interface Vessel {
  id: string;
  vessel_name: string;
  imo_number: string | null;
  shipping_line: string;
  port_of_loading: string;
  port_of_discharge: string;
  etd: string | null;
  atd: string | null;
  eta: string | null;
  status: string;
  updates: VesselUpdate[];
}

export interface BillOfLading {
  id: string;
  bl_number: string;
  bl_date: string;
  shipper_name: string;
  consignee_name: string;
  port_of_loading: string;
  port_of_discharge: string;
  container_count: number;
  commodity_description: string;
  gross_weight_kg: string;
  status: string;
  containers: Container[];
  vessel: Vessel | null;
  created_at: string;
}

export interface ShipmentLeg {
  id: string;
  booking_id: string;
  leg_index: number;
  vessel_name: string;
  imo_number: string | null;
  voyage_number: string | null;
  shipping_line: string;
  port_from: string;
  port_to: string;
  etd: string | null;
  atd: string | null;
  eta: string | null;
  ata: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClearingDocs {
  id: string;
  customs_entry_ref: string | null;
  hs_code: string | null;
  duty_rate: string | null;
  estimated_duty_vat: string | null;
  has_customs_entry: boolean;
  has_packing_list: boolean;
  has_certificate_of_origin: boolean;
  has_health_cert: boolean;
  status: string;
  updated_at: string;
}

export interface DeliverySchedule {
  id: string;
  delivery_date: string;
  time_window_start: string;
  time_window_end: string;
  haulier: string;
  driver_name: string | null;
  vehicle_reg: string | null;
  notes_to_recipient: string | null;
  status: string;
  delivered_at: string | null;
  failure_reason: string | null;
}

export interface DeliveryPoint {
  id: string;
  recipient_name: string;
  address: string;
  contact_name: string;
  contact_phone: string;
  special_instructions: string | null;
  status: string;
  delivery_type: 'direct' | 'via_warehouse' | null;
  warehouse_name: string | null;
  rebundled_at_warehouse: boolean;
  broker: Broker | null;
  end_company: Company | null;
  schedule: DeliverySchedule | null;
  containers: Container[];
  created_at: string;
}

export interface BookingDetail {
  id: string;
  reference: string;
  booking_number: string | null;
  status: BookingStatus;
  created_at: string;
  updated_at: string;
  purchase_orders: PurchaseOrder[];
  payments: SupplierPayment[];
  bill_of_lading: BillOfLading | null;
  clearing_docs: ClearingDocs | null;
  delivery_points: DeliveryPoint[];
  legs: ShipmentLeg[];
  gate_in_cutoff: string | null;
  empty_pickup_release: string | null;
  empty_return_deadline: string | null;
  free_days_detention: number | null;
  free_days_demurrage: number | null;
  detention_rate_gbp_after: string | null;
  demurrage_rate_gbp_after: string | null;
  port_of_discharge_terminal: string | null;
  service_mode: string | null;
}
