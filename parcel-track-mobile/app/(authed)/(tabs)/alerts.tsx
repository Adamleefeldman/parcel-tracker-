import { useRouter } from 'expo-router';
import React, { useCallback } from 'react';
import { FlatList, RefreshControl, StyleSheet, TouchableOpacity, View } from 'react-native';

import { useMarkNotificationRead } from '@/src/api/mutations/useMarkNotificationRead';
import { useNotifications } from '@/src/api/queries/useNotifications';
import type { NotificationOut } from '@/src/api/types/notification';
import { ErrorState, Pill, ScreenContainer, Spinner, Text } from '@/src/components/ui';
import { notificationLabel, notificationTone } from '@/src/features/alerts/notificationDisplay';
import { formatRelativeTime } from '@/src/lib/relativeTime';
import { colors, spacing } from '@/src/theme/tokens';

/**
 * Notifications feed. Single page of up to 50 (pull-to-refresh); load-more
 * pagination is a follow-up, so when more than a page exists a footer makes the
 * truncation explicit rather than implying the list is complete. Tapping a row
 * marks it read and, when the notification carries a `booking_id`, deep-links to
 * that booking. There is no mark-all-read endpoint, so that action is omitted.
 */
export default function AlertsScreen() {
  const router = useRouter();
  const { data, isLoading, isError, error, refetch, isRefetching } = useNotifications({
    limit: 50,
  });
  const markRead = useMarkNotificationRead();

  const onPressRow = useCallback(
    (n: NotificationOut) => {
      if (!n.read) markRead.mutate(n.id);
      if (n.booking_id) router.push(`/bookings/${n.booking_id}`);
    },
    [markRead, router],
  );

  const items = data?.items ?? [];

  return (
    <ScreenContainer padded={false}>
      <View style={styles.header}>
        <Text variant="display">Alerts</Text>
      </View>

      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(n) => n.id}
          renderItem={({ item }) => <AlertRow notification={item} onPress={onPressRow} />}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => refetch()} />}
          contentContainerStyle={items.length === 0 ? styles.emptyContainer : undefined}
          ListEmptyComponent={
            <Text muted style={styles.centeredText}>
              No alerts.
            </Text>
          }
          ListFooterComponent={
            data && data.total > items.length ? (
              <View style={styles.footer}>
                <Text variant="small" muted style={styles.centeredText}>
                  Showing the first {items.length} of {data.total} alerts.
                </Text>
              </View>
            ) : null
          }
        />
      )}
    </ScreenContainer>
  );
}

function AlertRow({
  notification,
  onPress,
}: {
  notification: NotificationOut;
  onPress: (n: NotificationOut) => void;
}) {
  const unread = !notification.read;
  return (
    <TouchableOpacity activeOpacity={0.7} onPress={() => onPress(notification)}>
      <View style={[styles.row, unread && styles.rowUnread]}>
        <View style={styles.rowHeader}>
          <Pill tone={notificationTone(notification.type)}>
            {notificationLabel(notification.type)}
          </Pill>
          <Text variant="small" muted>
            {formatRelativeTime(notification.created_at)}
          </Text>
        </View>
        <Text variant="body" numberOfLines={1} style={unread ? styles.unreadTitle : undefined}>
          {notification.title}
        </Text>
        <Text variant="small" muted numberOfLines={2}>
          {notification.message}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
  },
  row: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    backgroundColor: colors.bg,
    gap: spacing.xs,
  },
  rowUnread: {
    backgroundColor: colors.surface,
    borderLeftWidth: 3,
    borderLeftColor: colors.primary,
  },
  rowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  unreadTitle: {
    fontWeight: '700',
  },
  emptyContainer: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  footer: {
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
  },
  centeredText: {
    textAlign: 'center',
  },
});
