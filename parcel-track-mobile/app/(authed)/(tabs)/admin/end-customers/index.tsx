import { Stack, useRouter } from 'expo-router';
import React from 'react';
import { FlatList, RefreshControl, StyleSheet } from 'react-native';

import { useCompanies } from '@/src/api/queries/useCompanies';
import type { Company } from '@/src/api/types/admin';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import { Button, ErrorState, ListItem, ScreenContainer, Spinner, Text } from '@/src/components/ui';
import { spacing } from '@/src/theme/tokens';

/**
 * End customers (companies) list (admin → Operations). Create + read only — the
 * backend exposes no company PATCH/DELETE, so rows are display-only. "Add
 * customer" opens the create modal.
 */
export default function EndCustomersScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = canManageAdmin(user?.role as UserRole | undefined);
  const { data, isLoading, isError, error, refetch, isRefetching } = useCompanies({
    enabled: isAdmin,
    filters: { limit: 200 },
  });

  if (!isAdmin) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'End customers' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to manage end customers.
        </Text>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen
        options={{
          title: 'End customers',
          headerRight: () => (
            <Button
              title="Add"
              variant="ghost"
              onPress={() => router.push('/admin/end-customers/new')}
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
          data={data?.items ?? []}
          keyExtractor={(c) => c.id}
          renderItem={({ item }) => <CompanyRow company={item} />}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text muted style={styles.centeredText}>
              No end customers yet. Tap Add to create one.
            </Text>
          }
          ListFooterComponent={
            data && data.total > data.items.length ? (
              <Text variant="small" muted style={styles.footer}>
                Showing the first {data.items.length} of {data.total} customers.
              </Text>
            ) : null
          }
        />
      )}
    </ScreenContainer>
  );
}

function CompanyRow({ company }: { company: Company }) {
  return <ListItem title={company.legal_name} subtitle={companySubtitle(company)} />;
}

/** Compact one-line summary: aliases (if any) + VAT (if any). */
function companySubtitle(company: Company): string {
  const parts: string[] = [];
  if (company.aliases && company.aliases.length > 0) {
    parts.push(`aka ${company.aliases.join(', ')}`);
  }
  if (company.vat_no) {
    parts.push(`VAT ${company.vat_no}`);
  }
  return parts.length > 0 ? parts.join(' · ') : 'No aliases or VAT on file';
}

const styles = StyleSheet.create({
  listContent: {
    paddingBottom: spacing.xxl,
    flexGrow: 1,
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
