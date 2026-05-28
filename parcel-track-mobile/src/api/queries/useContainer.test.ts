/**
 * Tests for the container-finder helper used by `useContainer`.
 *
 * Containers can appear under `bill_of_lading.containers` OR under any
 * `delivery_points[].containers`, and the same container can show up in
 * both lists. The finder must:
 *   1. Return the container when only present under BL.
 *   2. Return the container when only present under a delivery point.
 *   3. Return one (deduped) when present in both.
 *   4. Return undefined for unknown IDs.
 *   5. Return undefined when booking or id is missing.
 */

import type { BookingDetail } from '../types/booking';
import type { Container } from '../types/container';
import { findContainerInBooking } from './useContainer';

function makeContainer(id: string, overrides: Partial<Container> = {}): Container {
  return {
    id,
    container_number: `MSCU${id}`,
    seal_number: null,
    port_status: 'not_arrived',
    status: 'created',
    lifecycle_status: 'ordered',
    destin8_ref: null,
    notes: null,
    delivery_type: null,
    broker: null,
    end_company: null,
    sale_price_per_tray: null,
    sale_price_per_pallet: null,
    sale_price_total: null,
    sale_currency: 'GBP',
    dispute_reason: null,
    disputed_at: null,
    dispute_acknowledged_at: null,
    dispute_acknowledged_by: null,
    updated_at: '2026-05-27T00:00:00Z',
    ...overrides,
  };
}

function makeBooking(opts: {
  blContainers?: Container[];
  dpContainers?: Container[][];
}): BookingDetail {
  return {
    id: 'b1',
    reference: 'REF',
    booking_number: null,
    status: 'draft',
    created_at: '2026-05-27T00:00:00Z',
    updated_at: '2026-05-27T00:00:00Z',
    purchase_orders: [],
    payments: [],
    bill_of_lading: opts.blContainers
      ? {
          id: 'bl1',
          bl_number: 'BL1',
          bl_date: '2026-05-01',
          shipper_name: 'X',
          consignee_name: 'Y',
          port_of_loading: 'Casablanca',
          port_of_discharge: 'felixstowe',
          container_count: opts.blContainers.length,
          commodity_description: 'C',
          gross_weight_kg: '1000',
          status: 'uploaded',
          containers: opts.blContainers,
          vessel: null,
          created_at: '2026-05-01T00:00:00Z',
        }
      : null,
    clearing_docs: null,
    delivery_points: (opts.dpContainers ?? []).map((containers, i) => ({
      id: `dp${i}`,
      recipient_name: 'R',
      address: 'A',
      contact_name: 'C',
      contact_phone: '0',
      special_instructions: null,
      status: 'awaiting_schedule',
      delivery_type: null,
      warehouse_name: null,
      rebundled_at_warehouse: false,
      broker: null,
      end_company: null,
      schedule: null,
      containers,
      created_at: '2026-05-01T00:00:00Z',
    })),
    legs: [],
    gate_in_cutoff: null,
    empty_pickup_release: null,
    empty_return_deadline: null,
    free_days_detention: null,
    free_days_demurrage: null,
    detention_rate_gbp_after: null,
    demurrage_rate_gbp_after: null,
    port_of_discharge_terminal: null,
    service_mode: null,
  };
}

describe('findContainerInBooking', () => {
  it('finds a container under bill_of_lading.containers', () => {
    const c = makeContainer('c1');
    const booking = makeBooking({ blContainers: [c] });
    expect(findContainerInBooking(booking, 'c1')).toBe(c);
  });

  it('finds a container under delivery_points[].containers when BL is null', () => {
    const c = makeContainer('c2');
    const booking = makeBooking({ dpContainers: [[c]] });
    expect(findContainerInBooking(booking, 'c2')).toBe(c);
  });

  it('returns a single container (deduped) when present in both BL and a delivery point', () => {
    const cBL = makeContainer('c3', { container_number: 'BL_COPY' });
    const cDP = makeContainer('c3', { container_number: 'DP_COPY' });
    const booking = makeBooking({ blContainers: [cBL], dpContainers: [[cDP]] });
    // First hit wins (BL); the caller doesn't get a two-element array.
    expect(findContainerInBooking(booking, 'c3')).toBe(cBL);
  });

  it('returns undefined for an unknown id', () => {
    const booking = makeBooking({ blContainers: [makeContainer('c1')] });
    expect(findContainerInBooking(booking, 'nope')).toBeUndefined();
  });

  it('returns undefined when booking is undefined', () => {
    expect(findContainerInBooking(undefined, 'c1')).toBeUndefined();
  });

  it('returns undefined when container id is undefined', () => {
    const booking = makeBooking({ blContainers: [makeContainer('c1')] });
    expect(findContainerInBooking(booking, undefined)).toBeUndefined();
  });

  it('searches across multiple delivery points', () => {
    const target = makeContainer('c4');
    const booking = makeBooking({
      dpContainers: [[makeContainer('other')], [target]],
    });
    expect(findContainerInBooking(booking, 'c4')).toBe(target);
  });
});
