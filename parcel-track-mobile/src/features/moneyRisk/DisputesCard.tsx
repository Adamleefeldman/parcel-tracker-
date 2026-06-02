import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';

import type { DisputeSummary } from '../../api/types/moneyRisk';
import { Card, Pill, Text } from '../../components/ui';
import { colors, spacing } from '../../theme/tokens';
import { disputesTone } from './moneyRiskFormat';

/**
 * Disputes summary card — unacknowledged count + a healthy/attention tone. A
 * read-only health line; the open/acknowledge actions live on the container
 * detail screen (write actions are out of scope here).
 */
export function DisputesCard({ summary }: { summary: DisputeSummary }) {
  const tone = disputesTone(summary.unacknowledged_count);
  const healthy = summary.unacknowledged_count === 0;

  return (
    <Card style={styles.card}>
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
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  body: {
    flex: 1,
    gap: 2,
  },
});
