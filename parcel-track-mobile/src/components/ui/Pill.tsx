import React from 'react';
import { StyleSheet, View } from 'react-native';

import { colors, radii, spacing } from '../../theme/tokens';
import { Text } from './Text';

export type PillTone = 'default' | 'success' | 'warning' | 'error';

export interface PillProps {
  tone?: PillTone;
  children: React.ReactNode;
}

export function Pill({ tone = 'default', children }: PillProps) {
  const palette = palettes[tone];
  return (
    <View style={[styles.pill, { backgroundColor: palette.bg, borderColor: palette.border }]}>
      <Text variant="small" style={{ color: palette.text }}>
        {children}
      </Text>
    </View>
  );
}

const palettes: Record<PillTone, { bg: string; border: string; text: string }> = {
  default: { bg: colors.surface, border: colors.border, text: colors.text },
  success: { bg: '#e6f7ef', border: colors.success, text: colors.success },
  warning: { bg: '#fff4e0', border: colors.warning, text: colors.warning },
  error: { bg: '#fde6e6', border: colors.error, text: colors.error },
};

const styles = StyleSheet.create({
  pill: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radii.sm,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
});
