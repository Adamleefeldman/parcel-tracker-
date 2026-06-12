import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { colors, overlays, sizes, spacing } from '../../theme/tokens';
import { Text } from './Text';

export interface ListItemProps {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  onPress?: () => void;
  /** Render the title in Geist Mono (refs/IDs — container numbers, codes). */
  monoTitle?: boolean;
  /** Render the subtitle in Geist Mono (codes/refs on the second line). */
  monoSubtitle?: boolean;
}

export function ListItem({
  title,
  subtitle,
  right,
  onPress,
  monoTitle,
  monoSubtitle,
}: ListItemProps) {
  const content = (
    <View style={styles.row}>
      <View style={styles.text}>
        <Text variant="body" mono={monoTitle} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text variant="small" mono={monoSubtitle} muted numberOfLines={1} style={styles.subtitle}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      <View style={styles.right}>
        {right}
        {onPress ? <Ionicons name="chevron-forward" size={18} color={colors.ink4} /> : null}
      </View>
    </View>
  );

  if (!onPress) {
    return content;
  }
  return (
    <Pressable
      onPress={onPress}
      android_ripple={{ color: overlays.ripple }}
      style={({ pressed }) => (pressed && Platform.OS === 'ios' ? styles.pressedIos : undefined)}
    >
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: sizes.touchTarget,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
    backgroundColor: colors.bgElev,
  },
  text: {
    flex: 1,
    paddingRight: spacing.md,
  },
  subtitle: {
    marginTop: spacing.xs,
  },
  right: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  // Android gets the ripple; iOS keeps the old TouchableOpacity-style dim.
  pressedIos: {
    opacity: 0.7,
  },
});
