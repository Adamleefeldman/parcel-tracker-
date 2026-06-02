import React from 'react';
import { StyleSheet, View } from 'react-native';

import { colors, radii } from '../../theme/tokens';

/**
 * Thin determinate progress bar. `progress` is a 0..1 fraction (clamped).
 * Token-styled to match the banked-progress bar on the container screen.
 */
export interface ProgressBarProps {
  progress: number;
}

export function ProgressBar({ progress }: ProgressBarProps) {
  const pct = Math.round(Math.max(0, Math.min(1, progress)) * 100);
  return (
    <View style={styles.track}>
      <View style={[styles.fill, { width: `${pct}%` }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    height: 6,
    borderRadius: radii.pill,
    backgroundColor: colors.bgSunk,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: radii.pill,
    backgroundColor: colors.primary,
  },
});
