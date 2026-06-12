import { Stack } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, TouchableOpacity, View } from 'react-native';

import { useAuditLogs } from '@/src/api/queries/useAuditLogs';
import type { AuditLogEntry } from '@/src/api/types/admin';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import {
  animateLayout,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Pill,
  ScreenContainer,
  Spinner,
  Text,
} from '@/src/components/ui';
import { humanizeAction, prettyJson } from '@/src/lib/auditFormat';
import { formatRelativeTime } from '@/src/lib/relativeTime';
import { colors, radii, spacing } from '@/src/theme/tokens';

const PAGE = 25;

/**
 * Audit-log feed (Admin → System). Global, newest-first, append-only history.
 * Load-more grows the fetch window (`limit`); tapping a row expands it to show
 * the old→new snapshot (pretty-printed defensively — the values may be null or
 * non-JSON) plus the client IP. Read-only: the audit log is never mutated.
 */
export default function AuditLogScreen() {
  const { user } = useAuth();
  const isAdmin = canManageAdmin(user?.role as UserRole | undefined);
  const [limit, setLimit] = useState(PAGE);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const { data, isLoading, isError, error, refetch, isRefetching, isFetching } = useAuditLogs({
    enabled: isAdmin,
    filters: { limit },
  });

  const entries = data?.items ?? [];
  const hasMore = data ? data.total > entries.length : false;

  const toggle = useCallback((id: string) => {
    animateLayout();
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  if (!isAdmin) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Audit log' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to view the audit log.
        </Text>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen options={{ title: 'Audit log' }} />
      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <FlatList
          data={entries}
          keyExtractor={(e) => e.id}
          renderItem={({ item }) => (
            <AuditRow
              entry={item}
              expanded={expanded.has(item.id)}
              onToggle={() => toggle(item.id)}
            />
          )}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <EmptyState
              icon="document-text-outline"
              title="No audit entries yet"
              subtitle="State changes are recorded here automatically."
            />
          }
          ListFooterComponent={
            hasMore ? (
              <View style={styles.footer}>
                <Button
                  title={isFetching ? 'Loading…' : 'Load more'}
                  variant="secondary"
                  onPress={() => setLimit((l) => l + PAGE)}
                  disabled={isFetching}
                />
                <Text variant="small" muted style={styles.footerCount}>
                  Showing {entries.length} of {data?.total}
                </Text>
              </View>
            ) : entries.length > 0 ? (
              <Text variant="small" muted style={styles.footerCount}>
                {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
              </Text>
            ) : null
          }
        />
      )}
    </ScreenContainer>
  );
}

function AuditRow({
  entry,
  expanded,
  onToggle,
}: {
  entry: AuditLogEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  const oldValue = prettyJson(entry.old_value);
  const newValue = prettyJson(entry.new_value);

  return (
    <TouchableOpacity activeOpacity={0.7} onPress={onToggle}>
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <Pill tone="default">{entry.entity_type}</Pill>
          <Text variant="small" muted>
            {formatRelativeTime(entry.created_at)}
          </Text>
        </View>
        <Text variant="title" numberOfLines={expanded ? undefined : 1}>
          {humanizeAction(entry.action)}
        </Text>
        <Text variant="small" muted numberOfLines={1}>
          {entry.actor_name ?? 'System'}
        </Text>

        {expanded ? (
          <View style={styles.detail}>
            {oldValue ? (
              <View style={styles.detailBlock}>
                <Text variant="overline" muted>
                  Before
                </Text>
                <Text variant="small" mono style={styles.snapshot}>
                  {oldValue}
                </Text>
              </View>
            ) : null}
            {newValue ? (
              <View style={styles.detailBlock}>
                <Text variant="overline" muted>
                  After
                </Text>
                <Text variant="small" mono style={styles.snapshot}>
                  {newValue}
                </Text>
              </View>
            ) : null}
            {!oldValue && !newValue ? (
              <Text variant="small" muted>
                No value snapshot recorded.
              </Text>
            ) : null}
            <Text variant="small" muted>
              IP · {entry.ip_address ?? '—'}
            </Text>
          </View>
        ) : null}
      </Card>
    </TouchableOpacity>
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
    gap: spacing.xs,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  detail: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
    gap: spacing.sm,
  },
  detailBlock: {
    gap: spacing.xs,
  },
  snapshot: {
    backgroundColor: colors.bgSunk,
    borderRadius: radii.md,
    padding: spacing.sm,
  },
  footer: {
    paddingVertical: spacing.lg,
    gap: spacing.sm,
  },
  footerCount: {
    textAlign: 'center',
    paddingVertical: spacing.md,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
