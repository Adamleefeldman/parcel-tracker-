import React from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  TouchableOpacity,
  type TouchableOpacityProps,
  View,
} from 'react-native';

import { colors, radii, spacing, type as typo } from '../../theme/tokens';
import { Text } from './Text';

type Variant = 'primary' | 'secondary' | 'ghost';

export interface ButtonProps extends Omit<TouchableOpacityProps, 'children'> {
  title: string;
  variant?: Variant;
  loading?: boolean;
}

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
      style={[styles.base, variantStyles[variant], isDisabled && styles.disabled, style]}
      {...rest}
    >
      <View style={styles.content}>
        {loading ? (
          <ActivityIndicator color={labelColor[variant]} />
        ) : (
          <Text style={[styles.label, { color: labelColor[variant] }]}>{title}</Text>
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
    opacity: 0.6,
  },
  label: {
    ...typo.body,
    fontWeight: '600',
  },
});

const variantStyles = StyleSheet.create({
  primary: {
    backgroundColor: colors.primary,
  },
  secondary: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  ghost: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.primary,
  },
});

const labelColor: Record<Variant, string> = {
  primary: colors.primaryText,
  secondary: colors.text,
  ghost: colors.primary,
};
