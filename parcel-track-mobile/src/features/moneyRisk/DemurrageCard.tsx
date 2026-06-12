import React from 'react';
import { StyleSheet, View } from 'react-native';

import type { DemurrageCountdown, DemurrageSummary } from '../../api/types/moneyRisk';
import { Card, Pill, Text, type PillTone } from '../../components/ui';
import { formatMoney } from '../../lib/money';
import { colors, radii, sizes, spacing } from '../../theme/tokens';
import { demurrageTone, formatDaysRemaining } from './moneyRiskFormat';

/** Saturated dot/figure color per urgency. */
const TONE_COLOR: Record<PillTone, string> = {
  error: colors.red,
  warning: colors.amber,
  default: colors.ink3,
  success: colors.green,
  info: colors.info,
};

/** "{ref} · {port} · £95/d after" — port/rate omitted when absent. */
function subtitleFor(item: DemurrageCountdown): string {
  const parts = [item.container_number];
  if (item.port_of_discharge) parts.push(item.port_of_discharge);
  if (item.rate_gbp_after) parts.push(`${formatMoney(item.rate_gbp_after)}/day after`);
  return parts.join(' · ');
}

/**
 * Demurrage countdown card — soonest-expiring free-time headline plus a row per
 * arrived container. **Whole days only** (`days_remaining` has no hour
 * component — the backend `ata` is date-only); `formatDaysRemaining` renders
 * "Nd" / "Today" / "Expired", never fabricated hours.
 */
export function DemurrageCard({ summary }: { summary: DemurrageSummary }) {
  const soonest = summary.items[0];

  return (
    <Card style={styles.card}>
      <View style={styles.headerRow}>
        <Text variant="overline" muted>
          Demurrage countdown
        </Text>
        {summary.expiring_count > 0 ? (
          <Pill tone="warning">{`${summary.expiring_count} expiring`}</Pill>
        ) : null}
      </View>

      {soonest ? (
        <>
          <Text variant="display">{formatDaysRemaining(summary.soonest_days_remaining ?? 0)}</Text>
          <Text variant="small" muted>
            {subtitleFor(soonest)}
          </Text>

          <View style={styles.divider} />

          {summary.items.map((item) => {
            const tone = demurrageTone(item);
            return (
              <View key={item.container_id} style={styles.row}>
                <View style={styles.rowLeft}>
                  <View style={[styles.dot, { backgroundColor: TONE_COLOR[tone] }]} />
                  <Text variant="body" mono weight="medium" numberOfLines={1}>
                    {item.container_number}
                  </Text>
                  {item.port_of_discharge ? (
                    <Text variant="small" muted>
                      · {item.port_of_discharge}
                    </Text>
                  ) : null}
                </View>
                <Text variant="body" weight="medium" color={TONE_COLOR[tone]}>
                  {formatDaysRemaining(item.days_remaining)}
                </Text>
              </View>
            );
          })}
        </>
      ) : (
        <Text variant="body" muted>
          No arrived containers in demurrage.
        </Text>
      )}
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
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.xs,
    gap: spacing.sm,
  },
  rowLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    flexShrink: 1,
  },
  dot: {
    width: sizes.dotSm,
    height: sizes.dotSm,
    borderRadius: radii.pill,
  },
});
