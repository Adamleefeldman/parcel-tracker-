import React, { useState } from 'react';
import { StyleSheet, TouchableOpacity, View } from 'react-native';

import type { ARAgingSummary } from '../../api/types/moneyRisk';
import { Card, Pill, Text, type PillTone } from '../../components/ui';
import { formatMoney } from '../../lib/money';
import { colors, spacing } from '../../theme/tokens';
import { agedExposure, arBucketTone } from './moneyRiskFormat';

/** Saturated figure color per bucket urgency (text, not a pill fill). */
const FIGURE_COLOR: Record<PillTone, string> = {
  error: colors.red,
  warning: colors.amber,
  default: colors.ink,
  success: colors.green,
  info: colors.info,
};

function bucketLabel(label: string): string {
  return label === '60+' ? '60+ days' : `${label}d`;
}

/**
 * A/R aging card — the full unbanked-£ exposure, an aged-30+ highlight pill, the
 * four aging bands, and a tap-to-expand drill-in over the inline `containers`
 * array (no dedicated drill-in route exists yet). All money via `formatMoney`.
 */
export function ARAgingCard({ summary }: { summary: ARAgingSummary }) {
  const [expanded, setExpanded] = useState(false);
  const aged = agedExposure(summary.buckets);

  return (
    <Card style={styles.card}>
      <View style={styles.headerRow}>
        <Text variant="overline" muted>
          A/R aging
        </Text>
        {aged.count > 0 ? <Pill tone="error">{`${formatMoney(aged.amount)} aged`}</Pill> : null}
      </View>

      <Text variant="display">{formatMoney(summary.total_outstanding)}</Text>
      <Text variant="small" muted>
        {summary.container_count} container{summary.container_count === 1 ? '' : 's'} · delivered,
        not yet banked
      </Text>

      <View style={styles.divider} />

      {summary.buckets.map((bucket) => {
        const tone = arBucketTone(bucket.label);
        return (
          <View key={bucket.label} style={styles.bucketRow}>
            <Text variant="body" muted>
              {bucketLabel(bucket.label)}
            </Text>
            <Text variant="body" mono weight="medium" color={FIGURE_COLOR[tone]}>
              {formatMoney(bucket.amount)}
            </Text>
          </View>
        );
      })}

      {summary.container_count > 0 ? (
        <>
          <View style={styles.divider} />
          <TouchableOpacity
            activeOpacity={0.7}
            onPress={() => setExpanded((v) => !v)}
            style={styles.drillRow}
          >
            <Text variant="body">
              {expanded ? 'Hide' : 'See'} {summary.container_count} container
              {summary.container_count === 1 ? '' : 's'}
            </Text>
            <Text variant="body" muted>
              {expanded ? '▴' : '▾'}
            </Text>
          </TouchableOpacity>

          {expanded ? (
            <View style={styles.drillList}>
              {summary.containers.map((c) => (
                <View key={c.container_id} style={styles.containerRow}>
                  <View style={styles.containerLeft}>
                    <Text variant="body" mono weight="medium" numberOfLines={1}>
                      {c.container_number}
                    </Text>
                    <Text variant="small" muted>
                      {c.days_aged}d aged
                    </Text>
                  </View>
                  <Text variant="body" mono>
                    {formatMoney(c.sale_price_total)}
                  </Text>
                </View>
              ))}
              {summary.containers_truncated ? (
                <Text variant="small" muted style={styles.truncated}>
                  Showing the first {summary.containers.length} of {summary.container_count}.
                </Text>
              ) : null}
            </View>
          ) : null}
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
    justifyContent: 'space-between',
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.line,
    marginVertical: spacing.sm,
  },
  bucketRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.xs,
  },
  drillRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  drillList: {
    marginTop: spacing.sm,
    gap: spacing.sm,
  },
  containerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  containerLeft: {
    flexShrink: 1,
    gap: 2,
  },
  truncated: {
    marginTop: spacing.xs,
  },
});
