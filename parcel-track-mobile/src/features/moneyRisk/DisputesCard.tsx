import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, TouchableOpacity, View } from 'react-native';

import type { DisputeSummary } from '../../api/types/moneyRisk';
import { Card, Pill, Text } from '../../components/ui';
import { colors, spacing } from '../../theme/tokens';
import { disputesTone } from './moneyRiskFormat';

/**
 * Disputes summary card — unacknowledged count + a healthy/attention tone, plus
 * a tap-through row per **unacknowledged** disputed container. Tapping opens that
 * container's booking, where the dispute is acknowledged (the actual write action
 * lives on the container detail screen; this is the deep-link to it).
 *
 * Acknowledged disputes are counted but not listed — the booking-completion
 * blocker is already lifted, so there's nothing to action.
 */
export function DisputesCard({
  summary,
  onOpenBooking,
}: {
  summary: DisputeSummary;
  onOpenBooking: (bookingId: string) => void;
}) {
  const tone = disputesTone(summary.unacknowledged_count);
  const healthy = summary.unacknowledged_count === 0;
  const unacknowledged = (summary.items ?? []).filter((i) => !i.acknowledged);

  return (
    <Card style={styles.card}>
      <View style={styles.headerRow}>
        <Ionicons
          name={healthy ? 'checkmark-circle-outline' : 'alert-circle-outline'}
          size={22}
          color={healthy ? colors.green : colors.amber}
        />
        <View style={styles.body}>
          <Text variant="overline" muted>
            Disputes
          </Text>
          <Text variant="title">{summary.unacknowledged_count} unacknowledged</Text>
        </View>
        <Pill tone={tone}>{healthy ? 'healthy' : 'attention'}</Pill>
      </View>

      {unacknowledged.length > 0 ? (
        <>
          <View style={styles.divider} />
          {unacknowledged.map((c) => (
            <TouchableOpacity
              key={c.container_id}
              activeOpacity={0.7}
              onPress={() => onOpenBooking(c.booking_id)}
              style={styles.disputeRow}
            >
              <Text variant="body" mono weight="medium" numberOfLines={1} style={styles.disputeRef}>
                {c.container_number}
              </Text>
              <Text variant="body" color={colors.amberInk}>
                Review ›
              </Text>
            </TouchableOpacity>
          ))}
        </>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.xs,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  body: {
    flex: 1,
    gap: 2,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.line,
    marginVertical: spacing.sm,
  },
  disputeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  disputeRef: {
    flexShrink: 1,
  },
});
