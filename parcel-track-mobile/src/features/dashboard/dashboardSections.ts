/**
 * Role → dashboard sections selector. Pure and unit-tested so the per-role
 * dashboard is data, not branching JSX. Greeting is the role label only (no
 * `/me`, no name in the JWT). Emphasized statuses pick which count cards each
 * role sees; no cross-booking container rollups exist, so everything is at
 * booking grain (drill into a booking for containers).
 */

import type { BookingStatus, UserRole } from '../../api/types/enums';

export interface DashboardConfig {
  greeting: string;
  sectionTitle: string;
  emphasizedStatuses: BookingStatus[];
  emptyCopy: string;
}

const ALL_STATUSES: BookingStatus[] = [
  'draft',
  'po_submitted',
  'invoice_received',
  'payment_confirmed',
  'bl_issued',
  'in_transit',
  'cleared',
  'complete',
];

export function dashboardConfig(role: UserRole | undefined): DashboardConfig {
  switch (role) {
    case 'admin':
      return {
        greeting: 'Admin',
        sectionTitle: 'All bookings by status',
        emphasizedStatuses: ALL_STATUSES,
        emptyCopy: 'No bookings yet.',
      };
    case 'morocco_agent':
      return {
        greeting: 'Morocco logistics',
        sectionTitle: 'Origin & pre-shipment',
        emphasizedStatuses: [
          'draft',
          'po_submitted',
          'invoice_received',
          'payment_confirmed',
          'bl_issued',
        ],
        emptyCopy: "You don't have any bookings assigned to you yet.",
      };
    case 'uk_agent':
      return {
        greeting: 'UK clearing & delivery',
        sectionTitle: 'In transit & clearance',
        emphasizedStatuses: ['in_transit', 'cleared'],
        emptyCopy: "You don't have any bookings assigned to you yet.",
      };
    case 'customer':
      return {
        greeting: 'Customer',
        sectionTitle: 'Your shipments',
        emphasizedStatuses: ['in_transit', 'cleared', 'complete'],
        emptyCopy: "You don't have any bookings yet.",
      };
    default:
      // Undefined role (anonymous / undecodable token): restrictive, generic.
      return {
        greeting: 'Signed in',
        sectionTitle: 'Bookings by status',
        emphasizedStatuses: ALL_STATUSES,
        emptyCopy: 'No bookings yet.',
      };
  }
}
