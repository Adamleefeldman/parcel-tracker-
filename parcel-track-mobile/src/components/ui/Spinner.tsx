import React from 'react';
import { ActivityIndicator, StyleSheet, View, type ActivityIndicatorProps } from 'react-native';

import { colors } from '../../theme/tokens';

export interface SpinnerProps extends ActivityIndicatorProps {
  centered?: boolean;
}

export function Spinner({
  centered,
  size = 'large',
  color = colors.primary,
  ...rest
}: SpinnerProps) {
  if (centered) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size={size} color={color} {...rest} />
      </View>
    );
  }
  return <ActivityIndicator size={size} color={color} {...rest} />;
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
