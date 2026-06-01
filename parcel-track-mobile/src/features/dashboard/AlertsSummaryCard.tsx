import React from 'react';
import { StyleSheet, TouchableOpacity, View } from 'react-native';

import type { NotificationOut } from '../../api/types/notification';
import { Button, Card, Pill, Text } from '../../components/ui';
import { formatRelativeTime } from '../../lib/relativeTime';
import { spacing } from '../../theme/tokens';

export interface AlertsSummaryCardProps {
  unreadCount: number;
  recent: NotificationOut[];
  /** True when the unread-count or recent-notifications query failed. */
  isError?: boolean;
  /** Retry the failed notification queries (only relevant when `isError`). */
  onRetry?: () => void;
  onPress: () => void;
}

/**
 * Dashboard alerts teaser — unread count + the two most recent titles.
 *
 * On a notifications fetch failure it shows an explicit error + Retry rather
 * than a "0 unread / no recent alerts" state, which is indistinguishable from a
 * genuinely-empty inbox and would quietly hide that something broke.
 */
export function AlertsSummaryCard({
  unreadCount,
  recent,
  isError = false,
  onRetry,
  onPress,
}: AlertsSummaryCardProps) {
  if (isError) {
    // Not wrapped in the navigate-on-tap TouchableOpacity: the alerts list is
    // likely failing too, so keep the user here and offer a direct retry.
    return (
      <Card style={styles.card}>
        <View style={styles.header}>
          <Text variant="heading">Alerts</Text>
          <Pill tone="error">Error</Pill>
        </View>
        <Text variant="small" muted>
          Couldn&apos;t load alerts.
        </Text>
        {onRetry ? <Button title="Retry" variant="ghost" onPress={onRetry} /> : null}
      </Card>
    );
  }

  return (
    <TouchableOpacity activeOpacity={0.7} onPress={onPress}>
      <Card style={styles.card}>
        <View style={styles.header}>
          <Text variant="heading">Alerts</Text>
          {unreadCount > 0 ? (
            <Pill tone="warning">{`${unreadCount} unread`}</Pill>
          ) : (
            <Text variant="small" muted>
              All caught up
            </Text>
          )}
        </View>
        {recent.length === 0 ? (
          <Text variant="small" muted>
            No recent alerts.
          </Text>
        ) : (
          recent.slice(0, 2).map((n) => (
            <View key={n.id} style={styles.row}>
              <Text variant="body" numberOfLines={1} style={styles.title}>
                {n.title}
              </Text>
              <Text variant="small" muted>
                {formatRelativeTime(n.created_at)}
              </Text>
            </View>
          ))
        )}
      </Card>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  title: {
    flexShrink: 1,
  },
});
