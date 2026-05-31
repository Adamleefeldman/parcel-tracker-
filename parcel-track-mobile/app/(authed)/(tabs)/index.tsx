import { useRouter } from 'expo-router';
import React, { useCallback, useMemo } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { ApiError } from '@/src/api/client';
import { useBookings } from '@/src/api/queries/useBookings';
import { useNotifications } from '@/src/api/queries/useNotifications';
import { useUnreadCount } from '@/src/api/queries/useUnreadCount';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { Button, Card, Pill, ScreenContainer, Spinner, Text } from '@/src/components/ui';
import { AlertsSummaryCard } from '@/src/features/dashboard/AlertsSummaryCard';
import { StatusCountGrid } from '@/src/features/dashboard/StatusCountGrid';
import { dashboardConfig } from '@/src/features/dashboard/dashboardSections';
import { countByStatus, totalCount } from '@/src/lib/bookingStatusCounts';
import { spacing } from '@/src/theme/tokens';

/**
 * Role-aware home. A shared shell (greeting chip, alerts summary) plus a
 * status-count grid whose emphasized statuses come from `dashboardConfig(role)`
 * — the role differences are pure data (tested in dashboardSections.test.ts),
 * so one screen covers all four roles rather than four near-duplicate ones.
 *
 * Status counts are derived client-side from a single `limit=200` bookings
 * fetch (no faceted-count endpoint exists). When booking volume exceeds a page
 * the upgrade is N `status=X&limit=1` calls reading `total`.
 *
 * Greeting is the role label only — there is no `/me` endpoint and the JWT
 * carries no name.
 */
export default function DashboardScreen() {
  const router = useRouter();
  const { user, signOut } = useAuth();
  const config = dashboardConfig(user?.role as UserRole | undefined);

  const bookingsQuery = useBookings({ limit: 200 });
  const recentQuery = useNotifications({ limit: 5 });
  const unreadQuery = useUnreadCount();

  const counts = useMemo(
    () => countByStatus(bookingsQuery.data?.items ?? []),
    [bookingsQuery.data],
  );
  const total = totalCount(counts);

  const onRefresh = useCallback(() => {
    bookingsQuery.refetch();
    recentQuery.refetch();
    unreadQuery.refetch();
  }, [bookingsQuery, recentQuery, unreadQuery]);

  const refreshing =
    bookingsQuery.isRefetching || recentQuery.isRefetching || unreadQuery.isRefetching;

  return (
    <ScreenContainer padded={false}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <View style={styles.header}>
          <View style={styles.headerTop}>
            <Text variant="display">Dashboard</Text>
            <Button title="Sign out" variant="ghost" onPress={signOut} />
          </View>
          <Pill tone="default">{config.greeting}</Pill>
        </View>

        <View style={styles.section}>
          <AlertsSummaryCard
            unreadCount={unreadQuery.data ?? 0}
            recent={recentQuery.data?.items ?? []}
            onPress={() => router.push('/alerts')}
          />
        </View>

        {bookingsQuery.isLoading ? (
          <Spinner centered />
        ) : bookingsQuery.isError ? (
          <ErrorState error={bookingsQuery.error} onRetry={() => bookingsQuery.refetch()} />
        ) : total === 0 ? (
          <View style={styles.section}>
            <Card>
              <Text variant="body" muted>
                {config.emptyCopy}
              </Text>
            </Card>
          </View>
        ) : (
          <View style={styles.section}>
            <View style={styles.sectionHeaderRow}>
              <Text variant="heading">{config.sectionTitle}</Text>
              <Text variant="small" muted>
                {total} total
              </Text>
            </View>
            <StatusCountGrid
              statuses={config.emphasizedStatuses}
              counts={counts}
              onSelect={() => router.push('/bookings')}
            />
            <Button
              title="View all bookings"
              variant="secondary"
              onPress={() => router.push('/bookings')}
              style={styles.viewAll}
            />
          </View>
        )}
      </ScrollView>
    </ScreenContainer>
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

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: spacing.xxl,
  },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  headerTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  section: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  viewAll: {
    marginTop: spacing.sm,
  },
  centered: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    gap: spacing.md,
  },
  centeredText: {
    textAlign: 'center',
  },
});
