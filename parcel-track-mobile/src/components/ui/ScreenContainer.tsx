import React from 'react';
import { StyleSheet, View, type ViewProps } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, spacing } from '../../theme/tokens';

export interface ScreenContainerProps extends ViewProps {
  padded?: boolean;
}

export function ScreenContainer({ padded = true, style, children, ...rest }: ScreenContainerProps) {
  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={[styles.inner, padded && styles.padded, style]} {...rest}>
        {children}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  inner: {
    flex: 1,
  },
  padded: {
    paddingHorizontal: spacing.lg,
  },
});
