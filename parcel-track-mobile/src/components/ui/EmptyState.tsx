import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';

import { colors, spacing } from '../../theme/tokens';
import { Text } from './Text';

/**
 * Uniform empty-state block for lists and sections. Replaces the per-screen
 * hand-rolled "No X yet" `<Text>`s so every empty list reads the same:
 * optional muted icon, a title, optional subtitle with the call to action.
 *
 * Centers itself within whatever container it's given — list screens put it in
 * a `flexGrow: 1` content container so it sits mid-screen.
 */
export interface EmptyStateProps {
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle?: string;
}

export function EmptyState({ icon, title, subtitle }: EmptyStateProps) {
  return (
    <View style={styles.container}>
      {icon ? <Ionicons name={icon} size={32} color={colors.ink4} /> : null}
      <Text variant="title" style={styles.centered}>
        {title}
      </Text>
      {subtitle ? (
        <Text variant="small" muted style={styles.centered}>
          {subtitle}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xxl,
    paddingHorizontal: spacing.lg,
  },
  centered: {
    textAlign: 'center',
  },
});
