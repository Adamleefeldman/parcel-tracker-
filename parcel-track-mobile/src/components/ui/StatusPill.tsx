import React from 'react';

import type { BookingStatus, ContainerLifecycleStatus } from '../../api/types/enums';
import { Pill } from './Pill';
import { BOOKING_TONES, LIFECYCLE_TONES, humanizeStatus } from './statusPillMapping';

/**
 * Centralized status → pill. Every status badge in the app routes through
 * here so a new enum value can't render with one tone in one place and a
 * different tone elsewhere. Mappings + label helper live in
 * `statusPillMapping.ts` so they can be unit-tested under ts-jest.
 */

export type StatusPillProps =
  | { kind: 'booking'; status: BookingStatus }
  | { kind: 'lifecycle'; status: ContainerLifecycleStatus };

export function StatusPill(props: StatusPillProps) {
  const tone =
    props.kind === 'booking' ? BOOKING_TONES[props.status] : LIFECYCLE_TONES[props.status];
  return <Pill tone={tone}>{humanizeStatus(props.status)}</Pill>;
}
