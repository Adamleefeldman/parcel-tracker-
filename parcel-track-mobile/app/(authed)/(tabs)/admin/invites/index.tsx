import { Stack, useRouter } from 'expo-router';
import React from 'react';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';

import { useInvites } from '@/src/api/queries/useInvites';
import type { Invite } from '@/src/api/types/admin';
import { USER_ROLE_LABELS, type UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import {
  Button,
  Card,
  ErrorState,
  Pill,
  ScreenContainer,
  Spinner,
  Text,
} from '@/src/components/ui';
import { spacing } from '@/src/theme/tokens';

/**
 * Pending-invites list (Admin → People). Lists invites the backend filters to
 * `status=pending` (not used, not expired). "Send invite" opens the create
 * modal, which reuses `POST /auth/invite`. No revoke action — there's no
 * mutation endpoint for it this round.
 */
export default function InvitesScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = canManageAdmin(user?.role as UserRole | undefined);
  const { data, isLoading, isError, error, refetch, isRefetching } = useInvites({
    enabled: isAdmin,
    filters: { status: 'pending', limit: 200 },
  });

  const invites = data?.items ?? [];

  if (!isAdmin) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Invites' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to manage invites.
        </Text>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen
        options={{
          title: 'Invites',
          headerRight: () => (
            <Button
              title="Send"
              variant="ghost"
              onPress={() => router.push('/admin/invites/new')}
            />
          ),
        }}
      />
      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <FlatList
          data={invites}
          keyExtractor={(inv) => inv.id}
          renderItem={({ item }) => <InviteRow invite={item} />}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text muted style={styles.centeredText}>
              No pending invites. Tap Send to invite someone.
            </Text>
          }
          ListFooterComponent={
            data && data.total > invites.length ? (
              <Text variant="small" muted style={styles.footer}>
                Showing the first {invites.length} of {data.total} pending invites.
              </Text>
            ) : null
          }
        />
      )}
    </ScreenContainer>
  );
}

/** "Expires in N days" / "Expires today" / "Expired" from `expires_at`. */
function expiresLabel(invite: Invite, now: Date = new Date()): string {
  if (invite.expired) return 'Expired';
  const ms = new Date(invite.expires_at).getTime() - now.getTime();
  if (Number.isNaN(ms) || ms <= 0) return 'Expired';
  const days = Math.ceil(ms / 86_400_000);
  if (days <= 1) return 'Expires today';
  return `Expires in ${days} days`;
}

function InviteRow({ invite }: { invite: Invite }) {
  return (
    <Card style={styles.card}>
      <View style={styles.cardBody}>
        <Text variant="title" numberOfLines={1}>
          {invite.email}
        </Text>
        <Text variant="small" muted>
          {expiresLabel(invite)}
        </Text>
      </View>
      <Pill tone="default">{USER_ROLE_LABELS[invite.role]}</Pill>
    </Card>
  );
}

const styles = StyleSheet.create({
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
    flexGrow: 1,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  cardBody: {
    flex: 1,
    gap: 2,
  },
  centeredText: {
    textAlign: 'center',
    marginTop: spacing.xxl,
  },
  footer: {
    textAlign: 'center',
    paddingVertical: spacing.lg,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
