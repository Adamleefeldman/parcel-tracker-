import { Stack } from 'expo-router';
import React, { useMemo } from 'react';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';

import { useUsers } from '@/src/api/queries/useUsers';
import type { UserAdmin } from '@/src/api/types/admin';
import { USER_ROLE_LABELS, type UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import {
  Card,
  EmptyState,
  ErrorState,
  Pill,
  ScreenContainer,
  Spinner,
  Text,
} from '@/src/components/ui';
import { spacing } from '@/src/theme/tokens';

/**
 * Users list (Admin → People). Read-only — there are no user-management
 * mutations this round (revoke/deactivate/role-change are out of scope). Shows
 * a role/active summary computed client-side from the fetched page. The user
 * base is tiny, so one capped page (`limit: 200`) is fetched; a truncation
 * footer + caveat appears if the org ever outgrows that.
 */
export default function UsersScreen() {
  const { user } = useAuth();
  const isAdmin = canManageAdmin(user?.role as UserRole | undefined);
  const { data, isLoading, isError, error, refetch, isRefetching } = useUsers({
    enabled: isAdmin,
    filters: { limit: 200 },
  });

  const users = data?.items ?? [];
  const truncated = data ? data.total > users.length : false;

  const summary = useMemo(() => buildSummary(data?.items ?? []), [data?.items]);

  if (!isAdmin) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Users' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to view users.
        </Text>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen options={{ title: 'Users' }} />
      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <FlatList
          data={users}
          keyExtractor={(u) => u.id}
          renderItem={({ item }) => <UserRow user={item} />}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
          contentContainerStyle={styles.listContent}
          ListHeaderComponent={
            users.length > 0 ? (
              <Text variant="small" muted style={styles.summary}>
                {summary}
                {truncated ? ' (first page)' : ''}
              </Text>
            ) : null
          }
          ListEmptyComponent={
            <EmptyState
              icon="people-outline"
              title="No users yet"
              subtitle="Invited users appear here once they sign up."
            />
          }
          ListFooterComponent={
            truncated ? (
              <Text variant="small" muted style={styles.footer}>
                Showing the first {users.length} of {data?.total} users.
              </Text>
            ) : null
          }
        />
      )}
    </ScreenContainer>
  );
}

/** "N active · X admin · Y agent · Z customer" from the fetched page. */
function buildSummary(users: UserAdmin[]): string {
  const active = users.filter((u) => u.is_active).length;
  const admin = users.filter((u) => u.role === 'admin').length;
  const agent = users.filter((u) => u.role === 'morocco_agent' || u.role === 'uk_agent').length;
  const customer = users.filter((u) => u.role === 'customer').length;
  return `${active} active · ${admin} admin · ${agent} agent · ${customer} customer`;
}

function UserRow({ user }: { user: UserAdmin }) {
  return (
    <Card style={styles.card}>
      <View style={styles.cardBody}>
        <View style={styles.nameRow}>
          <Text variant="title" numberOfLines={1} style={styles.name}>
            {user.name}
          </Text>
          {!user.is_active ? <Pill tone="error">Inactive</Pill> : null}
        </View>
        <Text variant="small" muted numberOfLines={1}>
          {user.email}
        </Text>
      </View>
      <Pill tone="default">{USER_ROLE_LABELS[user.role]}</Pill>
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
  summary: {
    paddingBottom: spacing.xs,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  cardBody: {
    flex: 1,
    gap: spacing.xs,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  name: {
    flexShrink: 1,
  },
  footer: {
    textAlign: 'center',
    paddingVertical: spacing.lg,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
