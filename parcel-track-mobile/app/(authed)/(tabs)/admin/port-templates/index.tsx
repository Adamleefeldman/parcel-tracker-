import { Stack, useRouter } from 'expo-router';
import React from 'react';
import { ScrollView, StyleSheet, TouchableOpacity, View } from 'react-native';

import { usePortTemplates } from '@/src/api/queries/usePortTemplates';
import type { PortTemplate } from '@/src/api/types/admin';
import { UK_PORTS, UK_PORT_LABELS, type UKPort, type UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import { Card, ErrorState, Pill, ScreenContainer, Spinner, Text } from '@/src/components/ui';
import { formatMoney } from '@/src/lib/money';
import { spacing } from '@/src/theme/tokens';

/**
 * Port-templates list (admin → Operations). Renders **every** UK port (a fixed
 * enum), merging in any saved template; ports without a row show "Not set" and
 * still tap through to the edit form (which upserts). Edit-only — you don't
 * "create" a port. Rate fields are decimal strings → `formatMoney`, never
 * `parseFloat`; free-days are plain ints.
 */
export default function PortTemplatesScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = canManageAdmin(user?.role as UserRole | undefined);
  const { data, isLoading, isError, error, refetch } = usePortTemplates({ enabled: isAdmin });

  if (!isAdmin) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Port templates' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to manage port templates.
        </Text>
      </ScreenContainer>
    );
  }

  const byPort = new Map<UKPort, PortTemplate>();
  for (const t of data ?? []) byPort.set(t.port, t);

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen options={{ title: 'Port templates' }} />
      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <ScrollView contentContainerStyle={styles.scroll}>
          <Text variant="small" muted style={styles.intro}>
            Default detention &amp; demurrage free-days and post-free-time rates per UK discharge
            port. A new bill of lading inherits these onto its booking.
          </Text>
          {UK_PORTS.map((port) => (
            <PortRow
              key={port}
              port={port}
              template={byPort.get(port)}
              // Static modal route + `port` as a query param. A dynamic terminal
              // segment (`[port]`) doesn't reliably bind to useLocalSearchParams
              // for an explicitly-registered modal screen, so we pass it as a
              // search param, which always surfaces.
              onPress={() =>
                router.push({ pathname: '/admin/port-templates/edit', params: { port } })
              }
            />
          ))}
        </ScrollView>
      )}
    </ScreenContainer>
  );
}

function PortRow({
  port,
  template,
  onPress,
}: {
  port: UKPort;
  template: PortTemplate | undefined;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity activeOpacity={0.7} onPress={onPress}>
      <Card style={styles.row}>
        <View style={styles.rowBody}>
          <View style={styles.titleRow}>
            <Text variant="title">{UK_PORT_LABELS[port]}</Text>
            <Pill tone={template ? 'success' : 'default'}>{template ? 'Set' : 'Not set'}</Pill>
          </View>
          {template ? (
            <View style={styles.detail}>
              <RateLine
                label="Detention"
                days={template.free_days_detention}
                rate={template.detention_rate_gbp_after}
              />
              <RateLine
                label="Demurrage"
                days={template.free_days_demurrage}
                rate={template.demurrage_rate_gbp_after}
              />
            </View>
          ) : (
            <Text variant="small" muted>
              Not configured — tap to set free-days &amp; rates.
            </Text>
          )}
        </View>
        <Text variant="body" muted style={styles.chevron}>
          ›
        </Text>
      </Card>
    </TouchableOpacity>
  );
}

function RateLine({ label, days, rate }: { label: string; days: number; rate: string | null }) {
  return (
    <Text variant="small" muted>
      {label}: {days} free {days === 1 ? 'day' : 'days'}
      {rate ? ` · ${formatMoney(rate)}/day after` : ''}
    </Text>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  intro: {
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  rowBody: {
    flex: 1,
    gap: spacing.xs,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  detail: {
    gap: 2,
  },
  chevron: {
    fontSize: 22,
    lineHeight: 22,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
