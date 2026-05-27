import { Stack, useRouter } from 'expo-router';
import React, { useCallback } from 'react';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';

import { ApiError } from '../../../src/api/client';
import { type Booking, useBookings } from '../../../src/api/queries/useBookings';
import { useAuth } from '../../../src/auth/AuthContext';
import { Button, ListItem, Pill, type PillTone, ScreenContainer, Spinner, Text } from '../../../src/components/ui';
import { spacing } from '../../../src/theme/tokens';

export default function BookingsScreen() {
  const router = useRouter();
  const { signOut } = useAuth();
  const { data, isLoading, isError, error, refetch, isRefetching } = useBookings();

  const onItemPress = useCallback(
    (id: string) => router.push(`/(authed)/bookings/${id}`),
    [router],
  );

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen
        options={{
          title: 'Bookings',
          headerRight: () => <Button title="Sign out" variant="ghost" onPress={signOut} />,
        }}
      />
      <View style={styles.header}>
        <Text variant="display">Bookings</Text>
      </View>

      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState onRefresh={() => refetch()} refreshing={isRefetching} />
      ) : (
        <FlatList
          data={data.items}
          keyExtractor={(b) => b.id}
          renderItem={({ item }) => <BookingRow booking={item} onPress={onItemPress} />}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={() => refetch()} />
          }
        />
      )}
    </ScreenContainer>
  );
}

function BookingRow({ booking, onPress }: { booking: Booking; onPress: (id: string) => void }) {
  return (
    <ListItem
      title={booking.booking_number || booking.reference}
      subtitle={formatDate(booking.created_at)}
      right={<Pill tone={toneFor(booking.status)}>{booking.status}</Pill>}
      onPress={() => onPress(booking.id)}
    />
  );
}

function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : 'Something went wrong.';
  return (
    <View style={styles.centered}>
      <Text muted style={styles.centeredText}>
        {message}
      </Text>
      <Button title="Retry" variant="ghost" onPress={onRetry} />
    </View>
  );
}

function EmptyState({ onRefresh, refreshing }: { onRefresh: () => void; refreshing: boolean }) {
  return (
    <FlatList
      data={[]}
      keyExtractor={() => ''}
      renderItem={() => null}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      contentContainerStyle={styles.emptyContainer}
      ListEmptyComponent={
        <Text muted style={styles.centeredText}>
          No bookings yet
        </Text>
      }
    />
  );
}

function toneFor(status: string): PillTone {
  const s = status.toLowerCase();
  if (s.includes('cancel') || s.includes('reject') || s.includes('fail')) return 'error';
  if (s.includes('pending') || s.includes('progress') || s.includes('wait')) return 'warning';
  if (s.includes('complete') || s.includes('deliver') || s.includes('paid')) return 'success';
  return 'default';
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    gap: spacing.md,
  },
  centeredText: {
    textAlign: 'center',
  },
  emptyContainer: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
});
