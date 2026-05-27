import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { ApiError } from '../../../../src/api/client';
import { useBooking } from '../../../../src/api/queries/useBooking';
import type {
  BillOfLading,
  BookingDetail,
  DeliveryPoint,
  PurchaseOrder,
  ShipmentLeg,
} from '../../../../src/api/types/booking';
import type { Container } from '../../../../src/api/types/container';
import { AppHeader } from '../../../../src/components/AppHeader';
import {
  Button,
  Card,
  ListItem,
  ScreenContainer,
  Spinner,
  StatusPill,
  Text,
} from '../../../../src/components/ui';
import { spacing } from '../../../../src/theme/tokens';

export default function BookingDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data, isLoading, isError, error, refetch, isRefetching } = useBooking(id);

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen options={{ headerTitle: () => <AppHeader title="Booking" /> }} />
      {isLoading ? (
        <Spinner centered />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <ErrorState error={new Error('Booking not found.')} onRetry={() => refetch()} />
      ) : (
        <Body booking={data} refreshing={isRefetching} onRefresh={() => refetch()} />
      )}
    </ScreenContainer>
  );
}

function Body({
  booking,
  refreshing,
  onRefresh,
}: {
  booking: BookingDetail;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const router = useRouter();
  const onContainerPress = useCallback(
    (containerId: string) =>
      router.push(`/(authed)/bookings/${booking.id}/containers/${containerId}`),
    [router, booking.id],
  );

  return (
    <ScrollView
      contentContainerStyle={styles.scroll}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      <Header booking={booking} />
      <ConfirmationTerms booking={booking} />
      <VesselAndBL bl={booking.bill_of_lading} />
      <ContainersSection bl={booking.bill_of_lading} onContainerPress={onContainerPress} />
      <LegsSection legs={booking.legs} />
      <POsSection pos={booking.purchase_orders} />
      <DeliverySection points={booking.delivery_points} />
    </ScrollView>
  );
}

function Header({ booking }: { booking: BookingDetail }) {
  return (
    <View style={styles.headerBlock}>
      <Text variant="display">{booking.booking_number || booking.reference}</Text>
      <View style={styles.headerRow}>
        <StatusPill kind="booking" status={booking.status} />
        {booking.booking_number ? (
          <Text variant="small" muted>
            Ref {booking.reference}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

function ConfirmationTerms({ booking }: { booking: BookingDetail }) {
  const hasAny =
    booking.free_days_detention != null ||
    booking.free_days_demurrage != null ||
    booking.detention_rate_gbp_after != null ||
    booking.demurrage_rate_gbp_after != null ||
    booking.port_of_discharge_terminal != null ||
    booking.service_mode != null;
  if (!hasAny) return null;

  return (
    <Section title="Booking confirmation">
      <Grid>
        <KV label="Free days (detention)" value={fmt(booking.free_days_detention)} />
        <KV label="Free days (demurrage)" value={fmt(booking.free_days_demurrage)} />
        <KV
          label="Detention rate / day"
          value={booking.detention_rate_gbp_after ? `£${booking.detention_rate_gbp_after}` : '—'}
        />
        <KV
          label="Demurrage rate / day"
          value={booking.demurrage_rate_gbp_after ? `£${booking.demurrage_rate_gbp_after}` : '—'}
        />
        <KV label="Terminal" value={fmt(booking.port_of_discharge_terminal)} />
        <KV label="Service mode" value={fmt(booking.service_mode)} />
      </Grid>
    </Section>
  );
}

function VesselAndBL({ bl }: { bl: BillOfLading | null }) {
  if (!bl) return null;
  return (
    <Section title="Bill of lading">
      <Grid>
        <KV label="BL number" value={bl.bl_number} />
        <KV label="BL date" value={formatDate(bl.bl_date)} />
        <KV label="Port of loading" value={bl.port_of_loading} />
        <KV label="Port of discharge" value={bl.port_of_discharge} />
        <KV label="Commodity" value={bl.commodity_description} />
        <KV label="Gross weight" value={`${bl.gross_weight_kg} kg`} />
      </Grid>
      {bl.vessel ? (
        <View style={styles.vesselBlock}>
          <Text variant="heading" style={styles.subheading}>
            Vessel
          </Text>
          <Grid>
            <KV label="Name" value={bl.vessel.vessel_name} />
            <KV label="IMO" value={fmt(bl.vessel.imo_number)} />
            <KV label="Line" value={bl.vessel.shipping_line} />
            <KV label="ETD" value={formatDate(bl.vessel.etd)} />
            <KV label="ATD" value={formatDate(bl.vessel.atd)} />
            <KV label="ETA" value={formatDate(bl.vessel.eta)} />
          </Grid>
        </View>
      ) : null}
    </Section>
  );
}

function ContainersSection({
  bl,
  onContainerPress,
}: {
  bl: BillOfLading | null;
  onContainerPress: (id: string) => void;
}) {
  const containers = bl?.containers ?? [];
  if (containers.length === 0) return null;
  return (
    <View style={styles.sectionWide}>
      <Text variant="heading" style={styles.sectionHeading}>
        Containers ({containers.length})
      </Text>
      <Card style={styles.listCard}>
        {containers.map((c) => (
          <ContainerRow key={c.id} container={c} onPress={onContainerPress} />
        ))}
      </Card>
    </View>
  );
}

function ContainerRow({
  container,
  onPress,
}: {
  container: Container;
  onPress: (id: string) => void;
}) {
  const subtitle =
    (container.seal_number ? `Seal ${container.seal_number}` : null) ||
    container.delivery_type ||
    undefined;
  return (
    <ListItem
      title={container.container_number}
      subtitle={subtitle}
      right={<StatusPill kind="lifecycle" status={container.lifecycle_status} />}
      onPress={() => onPress(container.id)}
    />
  );
}

function LegsSection({ legs }: { legs: ShipmentLeg[] }) {
  if (legs.length === 0) return null;
  const sorted = [...legs].sort((a, b) => a.leg_index - b.leg_index);
  return (
    <Section title="Route history">
      {sorted.map((leg) => (
        <View key={leg.id} style={styles.legBlock}>
          <Text variant="body">
            {leg.leg_index}. {leg.vessel_name || 'Unknown vessel'}
          </Text>
          <Text variant="small" muted>
            {leg.port_from} → {leg.port_to}
          </Text>
          <Text variant="small" muted>
            ETD {formatDate(leg.etd)} · ATD {formatDate(leg.atd)} · ETA {formatDate(leg.eta)} · ATA{' '}
            {formatDate(leg.ata)}
          </Text>
        </View>
      ))}
    </Section>
  );
}

function POsSection({ pos }: { pos: PurchaseOrder[] }) {
  if (pos.length === 0) return null;
  return (
    <Section title={`Purchase orders (${pos.length})`}>
      {pos.map((po) => (
        <View key={po.id} style={styles.poRow}>
          <View style={styles.poRowText}>
            <Text variant="body">{po.po_number}</Text>
            <Text variant="small" muted>
              {po.product_description}
            </Text>
          </View>
          <Text variant="small" muted>
            {po.status}
          </Text>
        </View>
      ))}
    </Section>
  );
}

function DeliverySection({ points }: { points: DeliveryPoint[] }) {
  if (points.length === 0) return null;
  return (
    <Section title={`Delivery points (${points.length})`}>
      {points.map((dp) => (
        <View key={dp.id} style={styles.deliveryBlock}>
          <Text variant="body">{dp.recipient_name}</Text>
          <Text variant="small" muted>
            {dp.address}
          </Text>
          <Grid>
            <KV label="Broker" value={dp.broker?.name ?? '—'} />
            <KV label="End company" value={dp.end_company?.legal_name ?? '—'} />
            <KV label="Status" value={dp.status} />
            <KV
              label="Scheduled"
              value={dp.schedule ? formatDate(dp.schedule.delivery_date) : '—'}
            />
          </Grid>
        </View>
      ))}
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

function Grid({ children }: { children: React.ReactNode }) {
  return <View style={styles.grid}>{children}</View>;
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

function fmt(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—';
  return String(value);
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: spacing.xxl,
  },
  headerBlock: {
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
  sectionWide: {
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  sectionHeading: {
    paddingHorizontal: 0,
  },
  subheading: {
    marginTop: spacing.md,
  },
  listCard: {
    padding: 0,
    marginHorizontal: spacing.lg,
    overflow: 'hidden',
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
  vesselBlock: {
    gap: spacing.sm,
  },
  legBlock: {
    paddingVertical: spacing.sm,
    gap: spacing.xs,
  },
  poRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    gap: spacing.md,
  },
  poRowText: {
    flex: 1,
    gap: spacing.xs,
  },
  deliveryBlock: {
    paddingVertical: spacing.sm,
    gap: spacing.sm,
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
