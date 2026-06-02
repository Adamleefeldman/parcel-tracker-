import React from 'react';
import { StyleSheet, View } from 'react-native';

import type { BookingStatus } from '../../api/types/enums';
import { colors, radii, spacing } from '../../theme/tokens';
import { humanizeStatus } from './statusPillMapping';
import { Text } from './Text';

/**
 * Presentational booking-progress stepper — the prototype's segmented
 * DRAFT→…→DONE bar. Purely a function of the existing `BookingStatus`; it adds
 * no data and makes no requests. The eight booking stages are a fixed forward
 * sequence, so the position is just the status's index.
 *
 * `disputed` is a container side-state, not a booking status, so it never
 * appears here — the stepper only ever reflects `BookingStatus`.
 */

const STAGES: BookingStatus[] = [
  'draft',
  'po_submitted',
  'invoice_received',
  'payment_confirmed',
  'bl_issued',
  'in_transit',
  'cleared',
  'complete',
];

export interface BookingStepperProps {
  status: BookingStatus;
}

export function BookingStepper({ status }: BookingStepperProps) {
  const index = Math.max(0, STAGES.indexOf(status));
  const step = index + 1;
  const isComplete = status === 'complete';

  return (
    <View>
      <View style={styles.track}>
        {STAGES.map((stage, i) => (
          <View
            key={stage}
            style={[styles.segment, i <= index ? styles.segmentOn : styles.segmentOff]}
          />
        ))}
      </View>
      <Text variant="overline" muted style={styles.caption}>
        {isComplete ? 'Complete' : `Step ${step} of ${STAGES.length} · ${humanizeStatus(status)}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    flexDirection: 'row',
    gap: spacing.xs,
  },
  segment: {
    flex: 1,
    height: 4,
    borderRadius: radii.pill,
  },
  segmentOn: {
    backgroundColor: colors.primary,
  },
  segmentOff: {
    backgroundColor: colors.bgSunk,
  },
  caption: {
    marginTop: spacing.sm,
  },
});
