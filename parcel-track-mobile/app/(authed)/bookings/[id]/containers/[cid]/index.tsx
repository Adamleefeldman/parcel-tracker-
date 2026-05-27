import { Stack, useLocalSearchParams } from 'expo-router';
import React from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { ApiError } from '../../../../../../src/api/client';
import { useContainer } from '../../../../../../src/api/queries/useContainer';
import type { Container } from '../../../../../../src/api/types/container';
import { AppHeader } from '../../../../../../src/components/AppHeader';
import {
  Button,
  Card,
  ScreenContainer,
  Spinner,
  StatusPill,
  Text,
} from '../../../../../../src/components/ui';
import { colors, radii, spacing } from '../../../../../../src/theme/tokens';

export default function ContainerDetailScreen() {
  const { id, cid } = useLocalSearchParams<{ id: string; cid: string }>();
  const { data, isLoading, isError, error, refetch, isRefetching } = useContainer(id, cid);

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen options={{ headerTitle: () => <AppHeader title="Container" /> }} />
      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <ErrorState
          error={new Error('Container not found on this booking.')}
          onRetry={() => refetch()}
        />
      ) : (
        <Body container={data} refreshing={isRefetching} onRefresh={() => refetch()} />
      )}
    </ScreenContainer>
  );
}

function Body({
  container,
  refreshing,
  onRefresh,
}: {
  container: Container;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <ScrollView
      contentContainerStyle={styles.scroll}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      <View style={styles.header}>
        <Text variant="display">{container.container_number}</Text>
        <View style={styles.headerRow}>
          <StatusPill kind="lifecycle" status={container.lifecycle_status} />
          {container.seal_number ? (
            <Text variant="small" muted>
              Seal {container.seal_number}
            </Text>
          ) : null}
        </View>
      </View>

      <DisputeBanner container={container} />
      <SaleSection container={container} />
      <PartiesSection container={container} />
      <OperationsSection container={container} />
      <MetadataSection container={container} />
    </ScrollView>
  );
}

function DisputeBanner({ container }: { container: Container }) {
  if (!container.dispute_reason) return null;
  const acknowledged = !!container.dispute_acknowledged_at;
  return (
    <View style={styles.section}>
      <Card style={styles.disputeCard}>
        <Text variant="heading" style={styles.disputeHeading}>
          Disputed
        </Text>
        <Text variant="body" style={styles.disputeBody}>
          {container.dispute_reason}
        </Text>
        <Text variant="small" style={styles.disputeMeta}>
          Opened {formatDateTime(container.disputed_at)}
          {acknowledged
            ? ` · Acknowledged ${formatDateTime(container.dispute_acknowledged_at)}`
            : ' · Not yet acknowledged'}
        </Text>
      </Card>
    </View>
  );
}

function SaleSection({ container }: { container: Container }) {
  const hasSale =
    container.sale_price_total != null ||
    container.sale_price_per_tray != null ||
    container.sale_price_per_pallet != null;
  if (!hasSale) return null;
  return (
    <Section title="Sale">
      <Text variant="display">
        {container.sale_price_total
          ? formatMoney(container.sale_price_total, container.sale_currency)
          : '—'}
      </Text>
      <View style={styles.grid}>
        <KV
          label="Per pallet"
          value={
            container.sale_price_per_pallet
              ? formatMoney(container.sale_price_per_pallet, container.sale_currency)
              : '—'
          }
        />
        <KV
          label="Per tray"
          value={
            container.sale_price_per_tray
              ? formatMoney(container.sale_price_per_tray, container.sale_currency)
              : '—'
          }
        />
      </View>
    </Section>
  );
}

function PartiesSection({ container }: { container: Container }) {
  const { broker, end_company } = container;
  return (
    <Section title="Parties">
      <View style={styles.partyBlock}>
        <Text variant="small" muted>
          Broker
        </Text>
        {broker ? (
          <View style={styles.grid}>
            <KV label="Name" value={broker.name} />
            <KV label="Code" value={broker.code} />
            <KV label="Phone" value={broker.phone ?? '—'} />
          </View>
        ) : (
          <Text variant="body" muted>
            Not assigned
          </Text>
        )}
      </View>
      <View style={styles.partyBlock}>
        <Text variant="small" muted>
          End company
        </Text>
        {end_company ? (
          <View style={styles.grid}>
            <KV label="Legal name" value={end_company.legal_name} />
            <KV label="Registration no." value={end_company.registration_no ?? '—'} />
            <KV label="VAT no." value={end_company.vat_no ?? '—'} />
            <KV label="Address" value={end_company.default_address ?? '—'} />
            {end_company.aliases && end_company.aliases.length > 0 ? (
              <KV label="Aliases" value={end_company.aliases.join(', ')} />
            ) : null}
          </View>
        ) : (
          <Text variant="body" muted>
            Not assigned
          </Text>
        )}
      </View>
    </Section>
  );
}

function OperationsSection({ container }: { container: Container }) {
  return (
    <Section title="Operations">
      <View style={styles.grid}>
        <KV label="Status" value={container.status} />
        <KV label="Port status" value={container.port_status} />
        <KV label="Destin8 ref" value={container.destin8_ref ?? '—'} />
        <KV label="Delivery type" value={container.delivery_type ?? '—'} />
      </View>
      {container.notes ? (
        <View style={styles.notesBlock}>
          <Text variant="small" muted>
            Notes
          </Text>
          <Text variant="body">{container.notes}</Text>
        </View>
      ) : null}
    </Section>
  );
}

function MetadataSection({ container }: { container: Container }) {
  return (
    <Section title="Metadata">
      <KV label="Last updated" value={formatDateTime(container.updated_at)} />
    </Section>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text variant="heading" style={styles.sectionHeading}>
        {title}
      </Text>
      <Card>{children}</Card>
    </View>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.kv}>
      <Text variant="small" muted>
        {label}
      </Text>
      <Text variant="body">{value}</Text>
    </View>
  );
}

function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : 'Something went wrong.';
  return (
    <View style={styles.centered}>
      <Text muted style={styles.centeredText}>
        {message}
      </Text>
      <Button title="Retry" variant="ghost" onPress={onRetry} />
    </View>
  );
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatMoney(amount: string, currency: string): string {
  return `${currency} ${amount}`;
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: spacing.xxl,
  },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  section: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  sectionHeading: {
    paddingHorizontal: 0,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  kv: {
    minWidth: '45%',
    gap: spacing.xs,
  },
  notesBlock: {
    marginTop: spacing.md,
    gap: spacing.xs,
  },
  partyBlock: {
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  disputeCard: {
    backgroundColor: '#fde6e6',
    borderColor: colors.error,
    borderRadius: radii.md,
    gap: spacing.sm,
  },
  disputeHeading: {
    color: colors.error,
  },
  disputeBody: {
    color: colors.error,
  },
  disputeMeta: {
    color: colors.error,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    gap: spacing.md,
  },
  centeredText: {
    textAlign: 'center',
  },
});
