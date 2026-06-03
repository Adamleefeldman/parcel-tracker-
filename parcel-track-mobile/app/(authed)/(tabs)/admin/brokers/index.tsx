import { Stack, useRouter } from 'expo-router';
import React from 'react';
import { FlatList, RefreshControl, StyleSheet } from 'react-native';

import { useBrokers } from '@/src/api/queries/useBrokers';
import type { Broker } from '@/src/api/types/admin';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import { Button, ErrorState, ListItem, ScreenContainer, Spinner, Text } from '@/src/components/ui';
import { spacing } from '@/src/theme/tokens';

/**
 * Brokers list (admin → Operations). Create + read only — the backend exposes
 * no broker PATCH/DELETE, so rows are display-only and there's no edit screen.
 * "Add broker" opens the create modal.
 */
export default function BrokersScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = canManageAdmin(user?.role as UserRole | undefined);
  // One capped page; the list is small but show a truncation footer if not.
  const { data, isLoading, isError, error, refetch, isRefetching } = useBrokers({
    enabled: isAdmin,
    filters: { limit: 200 },
  });

  if (!isAdmin) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Brokers' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to manage brokers.
        </Text>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen
        options={{
          title: 'Brokers',
          headerRight: () => (
            <Button title="Add" variant="ghost" onPress={() => router.push('/admin/brokers/new')} />
          ),
        }}
      />
      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <FlatList
          data={data?.items ?? []}
          keyExtractor={(b) => b.id}
          renderItem={({ item }) => <BrokerRow broker={item} />}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text muted style={styles.centeredText}>
              No brokers yet. Tap Add to create one.
            </Text>
          }
          ListFooterComponent={
            data && data.total > data.items.length ? (
              <Text variant="small" muted style={styles.footer}>
                Showing the first {data.items.length} of {data.total} brokers.
              </Text>
            ) : null
          }
        />
      )}
    </ScreenContainer>
  );
}

function BrokerRow({ broker }: { broker: Broker }) {
  return (
    <ListItem title={`${broker.code} · ${broker.name}`} subtitle={broker.phone ?? 'No phone'} />
  );
}

const styles = StyleSheet.create({
  listContent: {
    paddingBottom: spacing.xxl,
    flexGrow: 1,
  },
  centeredText: {
    textAlign: 'center',
    marginTop: spacing.xxl,
  },
  footer: {
    textAlign: 'center',
    paddingVertical: spacing.lg,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
