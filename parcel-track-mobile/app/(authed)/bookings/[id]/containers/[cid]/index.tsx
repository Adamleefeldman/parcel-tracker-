import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React from 'react';
import { Alert, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { ApiError } from '../../../../../../src/api/client';
import { useAcknowledgeDispute } from '../../../../../../src/api/mutations/useAcknowledgeDispute';
import { useContainer } from '../../../../../../src/api/queries/useContainer';
import { useCustomerPaymentAggregate } from '../../../../../../src/api/queries/useCustomerPaymentAggregate';
import { useCustomerPayments } from '../../../../../../src/api/queries/useCustomerPayments';
import type { Container } from '../../../../../../src/api/types/container';
import type { CustomerPayment } from '../../../../../../src/api/types/payment';
import { useAuth } from '../../../../../../src/auth/AuthContext';
import {
  canManageCustomerPayments,
  canManageDisputes,
  canUpdatePortStatus,
} from '../../../../../../src/auth/permissions';
import type { UserRole } from '../../../../../../src/api/types/enums';
import { AppHeader } from '../../../../../../src/components/AppHeader';
import {
  Button,
  Card,
  Pill,
  ScreenContainer,
  Spinner,
  StatusPill,
  Text,
  useToast,
} from '../../../../../../src/components/ui';
import { humanizeStatus } from '../../../../../../src/components/ui/statusPillMapping';
import { formatMoney, parseRatio } from '../../../../../../src/lib/money';
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
        <Body
          container={data}
          bookingId={id}
          containerId={cid}
          refreshing={isRefetching}
          onRefresh={() => refetch()}
        />
      )}
    </ScreenContainer>
  );
}

function Body({
  container,
  bookingId,
  containerId,
  refreshing,
  onRefresh,
}: {
  container: Container;
  bookingId: string;
  containerId: string;
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
      <ActionsSection container={container} bookingId={bookingId} containerId={containerId} />
      <SaleSection container={container} />
      <PaymentsSection container={container} bookingId={bookingId} containerId={containerId} />
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

/**
 * Role-gated actions. Visibility here is cosmetic — the server is the real
 * gate (dispute endpoints are admin-only and 403 otherwise). See
 * `src/auth/permissions.ts`. Customers see nothing; the whole section
 * collapses when no action applies.
 */
function ActionsSection({
  container,
  bookingId,
  containerId,
}: {
  container: Container;
  bookingId: string;
  containerId: string;
}) {
  const router = useRouter();
  const { user } = useAuth();
  const { showToast } = useToast();
  const acknowledge = useAcknowledgeDispute(bookingId, containerId);
  const role = user?.role as UserRole | undefined;

  const showPortStatus = canUpdatePortStatus(role);
  const isAdmin = canManageDisputes(role);
  const disputed = !!container.dispute_reason;
  const acknowledged = !!container.dispute_acknowledged_at;

  const showOpenDispute = isAdmin && !disputed;
  const showAcknowledge = isAdmin && disputed && !acknowledged;

  if (!showPortStatus && !showOpenDispute && !showAcknowledge) {
    return null;
  }

  const base = `/bookings/${bookingId}/containers/${containerId}`;

  const onAcknowledge = () => {
    Alert.alert('Acknowledge dispute', 'Mark this dispute as acknowledged?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Acknowledge',
        onPress: () =>
          acknowledge.mutate(undefined, {
            onSuccess: () => showToast('Dispute acknowledged', 'success'),
            onError: (err) =>
              showToast(
                err instanceof ApiError ? err.message : 'Could not acknowledge dispute',
                'error',
              ),
          }),
      },
    ]);
  };

  return (
    <Section title="Actions">
      <View style={styles.actions}>
        {showPortStatus ? (
          <Button
            title="Update port status"
            variant="secondary"
            onPress={() => router.push(`${base}/port-status`)}
          />
        ) : null}
        {showOpenDispute ? (
          <Button
            title="Open dispute"
            variant="secondary"
            onPress={() => router.push(`${base}/dispute`)}
          />
        ) : null}
        {showAcknowledge ? (
          <Button
            title="Acknowledge dispute"
            onPress={onAcknowledge}
            loading={acknowledge.isPending}
            disabled={acknowledge.isPending}
          />
        ) : null}
      </View>
    </Section>
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
        {formatMoney(container.sale_price_total, container.sale_currency)}
      </Text>
      <View style={styles.grid}>
        <KV
          label="Per pallet"
          value={formatMoney(container.sale_price_per_pallet, container.sale_currency)}
        />
        <KV
          label="Per tray"
          value={formatMoney(container.sale_price_per_tray, container.sale_currency)}
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
        <KV label="Status" value={humanizeStatus(container.status)} />
        <KV label="Port status" value={humanizeStatus(container.port_status)} />
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

/**
 * Customer-payments view. All booking members see the aggregate + tranche
 * list; financial amounts are masked (null → "—") server-side for non-admins,
 * with a one-line hint. Only admins see "Record payment" (cosmetic — the
 * create endpoint is `require_admin` and 403s everyone else).
 *
 * "Fully banked" is read from `container.lifecycle_status === 'banked'` — the
 * authoritative server signal — never a client-side Decimal comparison. The
 * progress bar is the only place a money value is coerced to a number
 * (`parseRatio`), and only for a cosmetic width.
 */
function PaymentsSection({
  container,
  bookingId,
  containerId,
}: {
  container: Container;
  bookingId: string;
  containerId: string;
}) {
  const router = useRouter();
  const { user } = useAuth();
  const role = user?.role as UserRole | undefined;
  const isAdmin = canManageCustomerPayments(role);

  const aggQuery = useCustomerPaymentAggregate(bookingId, containerId);
  const listQuery = useCustomerPayments(bookingId, containerId);

  const currency = container.sale_currency;
  const agg = aggQuery.data;
  const payments = listQuery.data?.items ?? [];
  const fullyBanked = container.lifecycle_status === 'banked';
  const ratio = agg ? parseRatio(agg.total_banked, container.sale_price_total) : null;

  // Non-admins get null amounts back; detect masking from the first tranche so
  // we can show the hint once rather than a column of "—".
  const amountsMasked =
    !isAdmin && payments.length > 0 && payments.every((p) => p.amount_received === null);

  return (
    <Section title="Customer payments">
      {aggQuery.isError ? (
        <Text variant="body" muted>
          Couldn&apos;t load payments.
        </Text>
      ) : (
        <>
          <View style={styles.bankedRow}>
            <Text variant="body">
              {formatMoney(agg?.total_banked, currency)} banked
              {container.sale_price_total
                ? ` of ${formatMoney(container.sale_price_total, currency)}`
                : ''}
            </Text>
            {fullyBanked ? <Pill tone="success">Fully banked</Pill> : null}
          </View>

          {ratio !== null ? (
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${Math.round(ratio * 100)}%` }]} />
            </View>
          ) : null}

          <Text variant="small" muted>
            {agg?.tranche_count ?? payments.length}{' '}
            {(agg?.tranche_count ?? payments.length) === 1 ? 'tranche' : 'tranches'}
          </Text>
        </>
      )}

      {payments.length > 0 ? (
        <View style={styles.tranches}>
          {payments.map((p) => (
            <TrancheRow key={p.id} payment={p} currency={currency} />
          ))}
        </View>
      ) : !aggQuery.isLoading ? (
        <Text variant="body" muted style={styles.emptyTranches}>
          No payments recorded yet.
        </Text>
      ) : null}

      {amountsMasked ? (
        <Text variant="small" muted style={styles.maskHint}>
          Amounts hidden for your role.
        </Text>
      ) : null}

      {isAdmin ? (
        <Button
          title="Record payment"
          variant="secondary"
          onPress={() =>
            router.push(`/bookings/${bookingId}/containers/${containerId}/record-payment`)
          }
          style={styles.recordButton}
        />
      ) : null}
    </Section>
  );
}

function TrancheRow({ payment, currency }: { payment: CustomerPayment; currency: string }) {
  return (
    <View style={styles.trancheRow}>
      <View style={styles.trancheMain}>
        <Text variant="body">{formatMoney(payment.amount_received, currency)}</Text>
        <Text variant="small" muted>
          #{payment.tranche_index} · {humanizeStatus(payment.method)} ·{' '}
          {formatDate(payment.payment_date)}
        </Text>
      </View>
      <Text variant="small" muted>
        Banked {formatMoney(payment.banked_total, currency)}
      </Text>
    </View>
  );
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
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
  actions: {
    gap: spacing.sm,
  },
  bankedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  progressTrack: {
    height: 6,
    borderRadius: radii.sm,
    backgroundColor: colors.border,
    overflow: 'hidden',
    marginTop: spacing.sm,
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.success,
  },
  tranches: {
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  trancheRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.sm,
    gap: spacing.sm,
  },
  trancheMain: {
    gap: spacing.xs,
    flexShrink: 1,
  },
  emptyTranches: {
    marginTop: spacing.sm,
  },
  maskHint: {
    marginTop: spacing.sm,
  },
  recordButton: {
    marginTop: spacing.md,
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
