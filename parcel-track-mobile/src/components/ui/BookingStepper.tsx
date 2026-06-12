import React from 'react';
import { StyleSheet, View } from 'react-native';

import type { BookingStatus } from '../../api/types/enums';
import { BOOKING_STAGES, bookingStageIndex } from '../../features/bookings/bookingProgress';
import { colors, radii, sizes, spacing } from '../../theme/tokens';
import { humanizeStatus } from './statusPillMapping';
import { Text } from './Text';

/**
 * Presentational booking-progress stepper — the prototype's segmented
 * DRAFT→…→DONE bar. Purely a function of the existing `BookingStatus`; it adds
 * no data and makes no requests. The status→step mapping lives in
 * `src/features/bookings/bookingProgress.ts` (shared with `BookingCard`'s
 * compact progress bar — don't fork it).
 */

export interface BookingStepperProps {
  status: BookingStatus;
}

export function BookingStepper({ status }: BookingStepperProps) {
  const index = bookingStageIndex(status);
  const step = index + 1;
  const isComplete = status === 'complete';

  return (
    <View>
      <View style={styles.track}>
        {BOOKING_STAGES.map((stage, i) => (
          <View
            key={stage}
            style={[styles.segment, i <= index ? styles.segmentOn : styles.segmentOff]}
          />
        ))}
      </View>
      <Text variant="overline" muted style={styles.caption}>
        {isComplete
          ? 'Complete'
          : `Step ${step} of ${BOOKING_STAGES.length} · ${humanizeStatus(status)}`}
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
    height: sizes.trackMicro,
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
