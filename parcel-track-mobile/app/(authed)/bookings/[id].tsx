import { Stack, useLocalSearchParams } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';

import { ScreenContainer, Text } from '../../../src/components/ui';
import { spacing } from '../../../src/theme/tokens';

export default function BookingDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title: 'Booking' }} />
      <View style={styles.body}>
        <Text variant="heading">Booking {id}</Text>
        <Text muted>Detail coming soon.</Text>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  body: {
    paddingTop: spacing.lg,
    gap: spacing.sm,
  },
});
