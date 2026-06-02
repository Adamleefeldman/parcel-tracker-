import React from 'react';
import { StyleSheet, View, type ViewProps } from 'react-native';

import { colors, radii, shadows, spacing } from '../../theme/tokens';

/**
 * Elevated surface — white card on the warm paper bg, with the prototype's
 * soft drop shadow layered over a 1px hairline ring (RN can't do the ring via
 * shadow, so it's a real border).
 */
export function Card({ style, ...rest }: ViewProps) {
  return <View style={[styles.card, style]} {...rest} />;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgElev,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.lg,
    padding: spacing.lg,
    ...shadows.sh2,
  },
});
