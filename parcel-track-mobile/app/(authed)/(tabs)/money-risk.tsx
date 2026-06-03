import { useRouter } from 'expo-router';
import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { canSeeMoneyRisk, useMoneyRisk } from '@/src/api/queries/useMoneyRisk';
import { useAuth } from '@/src/auth/AuthContext';
import { ErrorState, ScreenContainer, Spinner, Text } from '@/src/components/ui';
import { ARAgingCard } from '@/src/features/moneyRisk/ARAgingCard';
import { DemurrageCard } from '@/src/features/moneyRisk/DemurrageCard';
import { DisputesCard } from '@/src/features/moneyRisk/DisputesCard';
import { spacing } from '@/src/theme/tokens';

/**
 * The "Alerts" tab — the **Money-risk** dashboard (NOT the notifications feed,
 * which now lives in the Inbox tab). A/R aging exposure, demurrage countdowns,
 * and dispute health, all from one `GET /money-risk` call.
 *
 * Gated to admin + uk_agent: the tab is hidden for other roles (`href: null` in
 * the tabs layout) and the query is `enabled`-gated so a hidden-tab role never
 * fires the doomed 403 request. A deep-linked non-allowed role gets a friendly
 * "not available" body (defense-in-depth; the server is the real gate).
 */
export default function MoneyRiskScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const allowed = canSeeMoneyRisk(user?.role);
  const { data, isLoading, isError, error, refetch, isRefetching } = useMoneyRisk({
    enabled: allowed,
  });

  const onRefresh = useCallback(() => refetch(), [refetch]);
  const onOpenBooking = useCallback(
    (bookingId: string) => router.push(`/bookings/${bookingId}`),
    [router],
  );

  return (
    <ScreenContainer padded={false}>
      <View style={styles.header}>
        <Text variant="display">Money risk</Text>
        <Text variant="small" muted>
          A/R · demurrage
        </Text>
      </View>

      {!allowed ? (
        <View style={styles.centered}>
          <Text muted style={styles.centeredText}>
            Money-risk isn&apos;t available for your role.
          </Text>
        </View>
      ) : isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : data ? (
        <ScrollView
          contentContainerStyle={styles.scroll}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={onRefresh} />}
        >
          <ARAgingCard summary={data.ar_aging} />
          <DemurrageCard summary={data.demurrage} />
          <DisputesCard summary={data.disputes} onOpenBooking={onOpenBooking} />
        </ScrollView>
      ) : null}
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    gap: spacing.xs,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.lg,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  centeredText: {
    textAlign: 'center',
  },
});
