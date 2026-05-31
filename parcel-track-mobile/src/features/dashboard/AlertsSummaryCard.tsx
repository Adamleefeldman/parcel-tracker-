import React from 'react';
import { StyleSheet, TouchableOpacity, View } from 'react-native';

import type { NotificationOut } from '../../api/types/notification';
import { Card, Pill, Text } from '../../components/ui';
import { formatRelativeTime } from '../../lib/relativeTime';
import { spacing } from '../../theme/tokens';

export interface AlertsSummaryCardProps {
  unreadCount: number;
  recent: NotificationOut[];
  onPress: () => void;
}

/** Dashboard alerts teaser — unread count + the two most recent titles. */
export function AlertsSummaryCard({ unreadCount, recent, onPress }: AlertsSummaryCardProps) {
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
