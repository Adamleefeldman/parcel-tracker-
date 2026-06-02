import React from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  TouchableOpacity,
  type TouchableOpacityProps,
  View,
} from 'react-native';

import { colors, radii, shadows, spacing } from '../../theme/tokens';
import { Text } from './Text';

type Variant = 'primary' | 'secondary' | 'ghost';

export interface ButtonProps extends Omit<TouchableOpacityProps, 'children'> {
  title: string;
  variant?: Variant;
  loading?: boolean;
}

/**
 * - primary   navy fill + white ink + resting card shadow (the solid CTA)
 * - secondary elevated white surface + hairline border (neutral action)
 * - ghost     transparent + navy outline (low-emphasis, e.g. "snooze")
 */
export function Button({
  title,
  variant = 'primary',
  loading,
  disabled,
  style,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <TouchableOpacity
      activeOpacity={0.7}
      disabled={isDisabled}
      style={[
        styles.base,
        variantStyles[variant],
        variant === 'primary' && shadows.sh2,
        isDisabled && styles.disabled,
        style,
      ]}
      {...rest}
    >
      <View style={styles.content}>
        {loading ? (
          <ActivityIndicator color={labelColor[variant]} />
        ) : (
          <Text variant="body" weight="semibold" color={labelColor[variant]}>
            {title}
          </Text>
        )}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radii.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  disabled: {
    opacity: 0.5,
  },
});

const variantStyles = StyleSheet.create({
  primary: {
    backgroundColor: colors.primary,
  },
  secondary: {
    backgroundColor: colors.bgElev,
    borderWidth: 1,
    borderColor: colors.line,
  },
  ghost: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.primary,
  },
});

const labelColor: Record<Variant, string> = {
  primary: colors.primaryInk,
  secondary: colors.ink,
  ghost: colors.primary,
};
