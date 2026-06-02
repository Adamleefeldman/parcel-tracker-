import React from 'react';
import { StyleSheet, TouchableOpacity, View } from 'react-native';

import type { MoneyRiskOut } from '../../api/types/moneyRisk';
import { Card, Text } from '../../components/ui';
import { formatMoney } from '../../lib/money';
import { colors, spacing } from '../../theme/tokens';
import { agedExposure, formatDaysRemaining } from './moneyRiskFormat';

/**
 * The two money hero cards on the Bookings-tab landing (admin / uk_agent only):
 * aged A/R exposure (£) and the soonest demurrage countdown. Both tap through to
 * the Alerts (Money-risk) tab. Sourced from the same `/money-risk` payload the
 * Money-risk screen uses (one shared query), so this is a compact summary, not a
 * second fetch. Money via `formatMoney`; demurrage in **whole days** (no hours).
 */
export function MoneyHeroCards({ data, onPress }: { data: MoneyRiskOut; onPress: () => void }) {
  const aged = agedExposure(data.ar_aging.buckets);
  const soonest = data.demurrage.items[0];

  return (
    <View style={styles.row}>
      <TouchableOpacity style={styles.cell} activeOpacity={0.7} onPress={onPress}>
        <Card style={styles.card}>
          <Text variant="overline" muted>
            A/R · aged 30+
          </Text>
          <Text variant="heading" color={colors.red}>
            {formatMoney(aged.amount)}
          </Text>
          <Text variant="small" muted>
            {aged.count} container{aged.count === 1 ? '' : 's'}
          </Text>
        </Card>
      </TouchableOpacity>

      <TouchableOpacity style={styles.cell} activeOpacity={0.7} onPress={onPress}>
        <Card style={styles.card}>
          <Text variant="overline" muted>
            Demurrage
          </Text>
          <Text variant="heading" color={soonest ? colors.amber : colors.ink3}>
            {soonest ? formatDaysRemaining(data.demurrage.soonest_days_remaining ?? 0) : '—'}
          </Text>
          <Text variant="small" muted numberOfLines={1}>
            {soonest
              ? [soonest.container_number, soonest.port_of_discharge].filter(Boolean).join(' · ')
              : 'None expiring'}
          </Text>
        </Card>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  cell: {
    flex: 1,
  },
  card: {
    gap: spacing.xs,
  },
});
