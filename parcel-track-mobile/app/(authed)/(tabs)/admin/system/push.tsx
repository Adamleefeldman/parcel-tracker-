import { Stack } from 'expo-router';
import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import type { NotificationType, UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import { Card, ScreenContainer, Text } from '@/src/components/ui';
import { NOTIFICATION_LABELS } from '@/src/features/alerts/notificationDisplay';
import { colors, spacing } from '@/src/theme/tokens';

/**
 * Static informational panel (Admin → System → Push notifications). Lists the
 * 15 `NotificationType` values + their human labels (reused from
 * `NOTIFICATION_LABELS`, the same map the Inbox feed uses — no retyping). No
 * fetch, no config: push templates/delivery aren't editable yet. The list is
 * the enum order preserved by `NOTIFICATION_LABELS`'s insertion order.
 */
const NOTIFICATION_ROWS = Object.entries(NOTIFICATION_LABELS) as [NotificationType, string][];

export default function PushNotificationsScreen() {
  const { user } = useAuth();

  if (!canManageAdmin(user?.role as UserRole | undefined)) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Push notifications' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to view this.
        </Text>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen options={{ title: 'Push notifications' }} />
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text variant="small" muted style={styles.intro}>
          The {NOTIFICATION_ROWS.length} notification types the backend can emit. Each is delivered
          in-app (Inbox) and via Expo push when the user has a registered device.
        </Text>

        <Card style={styles.card}>
          {NOTIFICATION_ROWS.map(([type, label], i) => (
            <View
              key={type}
              style={[styles.row, i === NOTIFICATION_ROWS.length - 1 && styles.rowLast]}
            >
              <Text variant="body">{label}</Text>
              <Text variant="small" muted mono>
                {type}
              </Text>
            </View>
          ))}
        </Card>

        <Text variant="small" muted style={styles.footer}>
          Delivered via Expo push · templates aren&apos;t editable from the app yet.
        </Text>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
  },
  intro: {
    lineHeight: 18,
  },
  card: {
    paddingVertical: 0,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  rowLast: {
    borderBottomWidth: 0,
  },
  footer: {
    textAlign: 'center',
    paddingTop: spacing.xs,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
