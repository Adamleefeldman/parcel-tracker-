import { useRouter } from 'expo-router';
import React, { useCallback } from 'react';
import { FlatList, RefreshControl, StyleSheet, TouchableOpacity, View } from 'react-native';

import { useMarkNotificationRead } from '@/src/api/mutations/useMarkNotificationRead';
import { useNotifications } from '@/src/api/queries/useNotifications';
import type { NotificationOut } from '@/src/api/types/notification';
import {
  Card,
  EmptyState,
  ErrorState,
  Pill,
  ScreenContainer,
  Spinner,
  Text,
} from '@/src/components/ui';
import { notificationLabel, notificationTone } from '@/src/features/alerts/notificationDisplay';
import { formatRelativeTime } from '@/src/lib/relativeTime';
import { colors, spacing } from '@/src/theme/tokens';

/**
 * Inbox — the notifications feed (this is the tab the in-app notification list
 * moved to in Phase 10; the "Alerts" tab is now the Money-risk dashboard). The
 * unread badge lives on this tab.
 *
 * Single page of up to 50 (pull-to-refresh); load-more pagination is a
 * follow-up, so a footer makes the truncation explicit. Tapping a row marks it
 * read and, when the notification carries a `booking_id`, deep-links to that
 * booking. No mark-all-read endpoint exists, so that action is omitted.
 *
 * Restyled to the prototype's Inbox card language. The prototype's richer Inbox
 * (severity tinting, snooze, per-card actions, entity refs, type/urgent/unread
 * filters) needs backend fields that don't exist yet — deferred to Phase 12.
 * This renders the current `NotificationOut` shape only.
 */
export default function InboxScreen() {
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
        <Text variant="display">Inbox</Text>
      </View>

      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(n) => n.id}
          renderItem={({ item }) => <InboxRow notification={item} onPress={onPressRow} />}
          contentContainerStyle={items.length === 0 ? styles.emptyContainer : styles.listContent}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => refetch()} />}
          ListEmptyComponent={
            <EmptyState
              icon="mail-open-outline"
              title="You're all caught up"
              subtitle="New notifications appear here."
            />
          }
          ListFooterComponent={
            data && data.total > items.length ? (
              <View style={styles.footer}>
                <Text variant="small" muted style={styles.centeredText}>
                  Showing the first {items.length} of {data.total}.
                </Text>
              </View>
            ) : null
          }
        />
      )}
    </ScreenContainer>
  );
}

function InboxRow({
  notification,
  onPress,
}: {
  notification: NotificationOut;
  onPress: (n: NotificationOut) => void;
}) {
  const unread = !notification.read;
  return (
    <TouchableOpacity activeOpacity={0.7} onPress={() => onPress(notification)}>
      <Card style={[styles.card, unread && styles.cardUnread]}>
        <View style={styles.cardHeader}>
          <Pill tone={notificationTone(notification.type)}>
            {notificationLabel(notification.type)}
          </Pill>
          <Text variant="small" muted>
            {formatRelativeTime(notification.created_at)}
          </Text>
        </View>
        <Text variant="title" weight={unread ? 'semibold' : 'medium'} numberOfLines={1}>
          {notification.title}
        </Text>
        <Text variant="small" muted numberOfLines={2}>
          {notification.message}
        </Text>
      </Card>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
  },
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
  },
  card: {
    gap: spacing.xs,
  },
  cardUnread: {
    borderLeftWidth: 3,
    borderLeftColor: colors.primary,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  emptyContainer: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  footer: {
    paddingTop: spacing.md,
  },
  centeredText: {
    textAlign: 'center',
  },
});
