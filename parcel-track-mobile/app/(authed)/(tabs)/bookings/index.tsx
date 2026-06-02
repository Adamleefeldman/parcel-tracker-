import { Stack, useRouter } from 'expo-router';
import React, { useCallback } from 'react';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';

import { type Booking, useBookings } from '@/src/api/queries/useBookings';
import { canSeeMoneyRisk, useMoneyRisk } from '@/src/api/queries/useMoneyRisk';
import type { BookingStatus, UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import {
  Button,
  ErrorState,
  ListItem,
  Pill,
  ScreenContainer,
  Spinner,
  StatusPill,
  Text,
} from '@/src/components/ui';
import { dashboardConfig } from '@/src/features/dashboard/dashboardSections';
import { MoneyHeroCards } from '@/src/features/moneyRisk/MoneyHeroCards';
import { formatDate } from '@/src/lib/date';
import { spacing } from '@/src/theme/tokens';

/**
 * Bookings tab — the app's landing screen (Phase 10 merged the standalone
 * "Today" dashboard into this list's header). The header carries a role
 * greeting and, for admin / uk_agent, the two money hero cards (aged A/R +
 * soonest demurrage) that tap through to the Alerts (Money-risk) tab. Below it,
 * the live bookings list.
 *
 * Deferred (→ roadmap): the prototype's "N things need you today" action banner
 * and the All / Active / Needs-me / Mine filter chips — those are cross-booking
 * "needs me" feature work, not part of this IA pass.
 */
export default function BookingsScreen() {
  const router = useRouter();
  const { signOut, user } = useAuth();
  const role = user?.role as UserRole | undefined;
  const config = dashboardConfig(role);

  // One capped page serves both the list and (future) overview; the list shows
  // a truncation footer if the server reports more than a page.
  const { data, isLoading, isError, error, refetch, isRefetching } = useBookings({ limit: 200 });
  const moneyRisk = useMoneyRisk({ enabled: canSeeMoneyRisk(role) });

  const onItemPress = useCallback((id: string) => router.push(`/bookings/${id}`), [router]);
  const onRefresh = useCallback(() => {
    refetch();
    if (canSeeMoneyRisk(role)) moneyRisk.refetch();
  }, [refetch, moneyRisk, role]);

  const header = (
    <View style={styles.header}>
      <Pill tone="default">{config.greeting}</Pill>
      {canSeeMoneyRisk(role) && moneyRisk.data ? (
        <MoneyHeroCards data={moneyRisk.data} onPress={() => router.push('/money-risk')} />
      ) : null}
      <Text variant="overline" muted style={styles.listLabel}>
        Bookings
      </Text>
    </View>
  );

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen
        options={{
          title: 'Bookings',
          headerRight: () => <Button title="Sign out" variant="ghost" onPress={signOut} />,
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
          ListHeaderComponent={header}
          renderItem={({ item }) => <BookingRow booking={item} onPress={onItemPress} />}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={onRefresh} />}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text muted style={styles.centeredText}>
              {emptyMessageFor(role)}
            </Text>
          }
          ListFooterComponent={
            data && data.total > data.items.length ? (
              <TruncationNotice shown={data.items.length} total={data.total} />
            ) : null
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
      right={<StatusPill kind="booking" status={booking.status as BookingStatus} />}
      onPress={() => onPress(booking.id)}
    />
  );
}

/**
 * Footer shown when the list is truncated to one page. The list isn't yet
 * paginated past the backend's default page, so make it explicit that more
 * bookings exist beyond what's shown rather than implying this is everything.
 */
function TruncationNotice({ shown, total }: { shown: number; total: number }) {
  return (
    <View style={styles.footer}>
      <Text variant="small" muted style={styles.centeredText}>
        Showing the first {shown} of {total} bookings.
      </Text>
    </View>
  );
}

function emptyMessageFor(role: string | undefined): string {
  if (role === 'admin') return 'No bookings yet. Create one from the dashboard.';
  // Most restrictive default — covers customer, agents, and the rare null user.
  return "You don't have any bookings assigned to you yet.";
}

const styles = StyleSheet.create({
  header: {
    paddingTop: spacing.lg,
    paddingBottom: spacing.sm,
    gap: spacing.md,
  },
  listLabel: {
    paddingTop: spacing.sm,
  },
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxl,
    flexGrow: 1,
  },
  footer: {
    paddingVertical: spacing.lg,
  },
  centeredText: {
    textAlign: 'center',
  },
});
