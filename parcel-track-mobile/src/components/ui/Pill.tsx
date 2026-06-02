import React from 'react';
import { StyleSheet, View } from 'react-native';

import { colors, radii, spacing } from '../../theme/tokens';
import { Text } from './Text';

export type PillTone = 'default' | 'success' | 'warning' | 'error' | 'info';

export interface PillProps {
  tone?: PillTone;
  children: React.ReactNode;
}

/**
 * Small status/label badge. Uses the soft/ink color convention (low-saturation
 * surface fill + high-contrast text) and the full pill radius — borderless, to
 * match the prototype. The single badge component for the app; status badges go
 * through `<StatusPill>`, which wraps this.
 */
export function Pill({ tone = 'default', children }: PillProps) {
  const palette = palettes[tone];
  return (
    <View style={[styles.pill, { backgroundColor: palette.bg }]}>
      <Text variant="overline" weight="semibold" color={palette.text} style={styles.label}>
        {children}
      </Text>
    </View>
  );
}

const palettes: Record<PillTone, { bg: string; text: string }> = {
  default: { bg: colors.bgSoft, text: colors.ink2 },
  success: { bg: colors.greenSoft, text: colors.greenInk },
  warning: { bg: colors.amberSoft, text: colors.amberInk },
  error: { bg: colors.redSoft, text: colors.redInk },
  info: { bg: colors.infoSoft, text: colors.infoInk },
};

const styles = StyleSheet.create({
  pill: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radii.pill,
    alignSelf: 'flex-start',
  },
  // Pills read better with normal casing than the overline's uppercase default
  // (status labels like "In transit" are humanized sentence-case).
  label: {
    textTransform: 'none',
    letterSpacing: 0.2,
    fontSize: 11,
    lineHeight: 14,
  },
});
