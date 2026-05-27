import React from 'react';
import { StyleSheet, Text as RNText, type TextProps as RNTextProps } from 'react-native';

import { colors, type } from '../../theme/tokens';

type Variant = 'body' | 'small' | 'heading' | 'display';

export interface TextProps extends RNTextProps {
  variant?: Variant;
  muted?: boolean;
}

export function Text({ variant = 'body', muted, style, ...rest }: TextProps) {
  return (
    <RNText
      style={[styles[variant], { color: muted ? colors.textMuted : colors.text }, style]}
      {...rest}
    />
  );
}

const styles = StyleSheet.create({
  body: type.body,
  small: type.small,
  heading: type.heading,
  display: type.display,
});
