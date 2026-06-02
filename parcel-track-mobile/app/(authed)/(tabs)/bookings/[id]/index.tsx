import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { useBooking } from '@/src/api/queries/useBooking';
import { useSupplierPayments } from '@/src/api/queries/useSupplierPayments';
import type {
  BillOfLading,
  BookingDetail,
  ClearingDocs,
  DeliveryPoint,
  PurchaseOrder,
  ShipmentLeg,
} from '@/src/api/types/booking';
import type { Container } from '@/src/api/types/container';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageSupplierPayments } from '@/src/auth/permissions';
import { AppHeader } from '@/src/components/AppHeader';
import { DocumentsList } from '@/src/components/documents/DocumentsList';
import {
  Button,
  Card,
  ErrorState,
  ListItem,
  ProgressBar,
  ScreenContainer,
  Spinner,
  StatusPill,
  Text,
} from '@/src/components/ui';
import { formatDate, formatDateTime } from '@/src/lib/date';
import { formatMoney, parseRatio, sumDecimalStrings } from '@/src/lib/money';
import { colors, spacing } from '@/src/theme/tokens';

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
    (containerId: string) => router.push(`/bookings/${booking.id}/containers/${containerId}`),
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
      {/* The arrays below are non-null in the typed schema, but defend against a
          null from the wire — `null.length` would crash the whole screen. */}
      <LegsSection legs={booking.legs ?? []} />
      <POsSection pos={booking.purchase_orders ?? []} bookingId={booking.id} />
      <ClearingDocsSection docs={booking.clearing_docs} />
      <DeliverySection points={booking.delivery_points ?? []} />
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
    booking.service_mode != null ||
    booking.gate_in_cutoff != null ||
    booking.empty_pickup_release != null ||
    booking.empty_return_deadline != null;
  if (!hasAny) return null;

  return (
    <Section title="Booking confirmation">
      <Grid>
        <KV label="Free days (detention)" value={fmt(booking.free_days_detention)} />
        <KV label="Free days (demurrage)" value={fmt(booking.free_days_demurrage)} />
        <KV
          label="Detention rate / day"
          value={formatMoney(booking.detention_rate_gbp_after, 'GBP')}
        />
        <KV
          label="Demurrage rate / day"
          value={formatMoney(booking.demurrage_rate_gbp_after, 'GBP')}
        />
        <KV label="Terminal" value={fmt(booking.port_of_discharge_terminal)} />
        <KV label="Service mode" value={fmt(booking.service_mode)} />
        <KV label="Gate-in cutoff" value={formatDateTime(booking.gate_in_cutoff)} />
        <KV label="Empty pickup release" value={formatDateTime(booking.empty_pickup_release)} />
        <KV label="Empty return deadline" value={formatDateTime(booking.empty_return_deadline)} />
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
        <KV label="Status" value={bl.status} />
        <KV label="Containers" value={String(bl.container_count)} />
        <KV label="Port of loading" value={bl.port_of_loading} />
        <KV label="Port of discharge" value={bl.port_of_discharge} />
        <KV label="Shipper" value={bl.shipper_name} />
        <KV label="Consignee" value={bl.consignee_name} />
        <KV label="Commodity" value={bl.commodity_description} />
        <KV label="Gross weight" value={`${bl.gross_weight_kg} kg`} />
        <KV label="Issued" value={formatDate(bl.created_at)} />
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
            <KV label="Status" value={bl.vessel.status} />
            <KV label="ETD" value={formatDate(bl.vessel.etd)} />
            <KV label="ATD" value={formatDate(bl.vessel.atd)} />
            <KV label="ETA" value={formatDate(bl.vessel.eta)} />
          </Grid>
        </View>
      ) : null}
      <DocumentsList entityType="bill_of_lading" entityId={bl.id} label="Bill of lading" />
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
      <Text variant="heading" style={styles.sectionHeadingPadded}>
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
      {sorted.map((leg, i) => (
        <View key={leg.id} style={[styles.legBlock, i < sorted.length - 1 && styles.dividerBottom]}>
          <Text variant="body">
            {leg.leg_index}. {leg.vessel_name || 'Unknown vessel'}
            {leg.voyage_number ? ` · voy ${leg.voyage_number}` : ''}
          </Text>
          <Text variant="small" muted>
            {leg.shipping_line || 'Unknown line'} · {leg.port_from} → {leg.port_to}
            {leg.imo_number ? ` · IMO ${leg.imo_number}` : ''}
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

function POsSection({ pos, bookingId }: { pos: PurchaseOrder[]; bookingId: string }) {
  if (pos.length === 0) return null;
  return (
    <Section title={`Purchase orders (${pos.length})`}>
      {pos.map((po, i) => (
        <View key={po.id} style={[styles.poBlock, i < pos.length - 1 && styles.dividerBottom]}>
          <View style={styles.poHeaderRow}>
            <Text variant="body">{po.po_number}</Text>
            <Text variant="small" muted>
              {po.status}
            </Text>
          </View>
          <Text variant="small" muted>
            {po.product_description}
          </Text>
          <Grid>
            <KV label="PO date" value={formatDate(po.po_date)} />
            <KV label="Quantity" value={`${po.quantity} ${po.quantity_unit}`} />
            <KV label="Total value" value={formatMoney(po.total_value, po.currency)} />
            <KV label="Notes" value={fmt(po.notes)} />
          </Grid>
          <DocumentsList
            entityType="purchase_order"
            entityId={po.id}
            label={`PO ${po.po_number}`}
          />
          {po.invoice ? <InvoiceBlock invoice={po.invoice} bookingId={bookingId} /> : null}
        </View>
      ))}
    </Section>
  );
}

function InvoiceBlock({
  invoice,
  bookingId,
}: {
  invoice: NonNullable<PurchaseOrder['invoice']>;
  bookingId: string;
}) {
  return (
    <View style={styles.invoiceBlock}>
      <View style={styles.poHeaderRow}>
        <Text variant="small" muted>
          Invoice {invoice.invoice_number}
        </Text>
        <Text variant="small" muted>
          {invoice.status}
          {invoice.discrepancy_acknowledged ? ' · ack' : ''}
        </Text>
      </View>
      <Grid>
        <KV label="Invoice date" value={formatDate(invoice.invoice_date)} />
        <KV label="Value" value={formatMoney(invoice.value, invoice.currency)} />
        <KV label="Terms" value={fmt(invoice.payment_terms)} />
        <KV label="Due" value={formatDate(invoice.due_date)} />
      </Grid>
      <DocumentsList
        entityType="invoice"
        entityId={invoice.id}
        label={`Invoice ${invoice.invoice_number}`}
      />
      <SupplierPaymentsSection
        invoiceId={invoice.id}
        invoiceValue={invoice.value}
        currency={invoice.currency}
        bookingId={bookingId}
      />
    </View>
  );
}

/**
 * Supplier payments for one invoice — money OUT (outbound USD wires). Entirely
 * **admin-only**: the create AND list endpoints are `require_admin`, so a
 * non-admin sees nothing here and the list query is gated with
 * `enabled: isAdmin` so it never fires a doomed 403. There is deliberately no
 * masked read for non-admins (unlike customer payments).
 *
 * Per-invoice progress only: "Paid X of Y" sums this invoice's confirmed
 * payments (Decimal-safe `sumDecimalStrings`, never a float reduce) against the
 * invoice `value`. The booking lifecycle pill conveys the booking-level state —
 * recording enough to clear the invoices auto-advances it to `payment_confirmed`
 * server-side, surfaced by the booking invalidation in the create mutation.
 */
function SupplierPaymentsSection({
  invoiceId,
  invoiceValue,
  currency,
  bookingId,
}: {
  invoiceId: string;
  invoiceValue: string | null;
  currency: string;
  bookingId: string;
}) {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = canManageSupplierPayments(user?.role as UserRole | undefined);

  const { data, isLoading, isError } = useSupplierPayments(invoiceId, { enabled: isAdmin });

  if (!isAdmin) return null;

  const payments = data?.items ?? [];
  const totalPaid = sumDecimalStrings(payments.map((p) => p.amount));
  const ratio = parseRatio(totalPaid, invoiceValue);
  // The "Paid X of Y" total sums only the fetched payments. We request a high
  // limit so this is the whole list in practice, but if the server reports more
  // than we fetched, the sum is partial — say so rather than under-count.
  const fetchedCount = payments.length;
  const totalCount = data?.total ?? fetchedCount;
  const isPartial = totalCount > fetchedCount;

  return (
    <View style={styles.supplierPaymentsBlock}>
      <Text variant="small" muted>
        Supplier payments
      </Text>

      {isError ? (
        <Text variant="body" muted>
          Couldn&apos;t load payments.
        </Text>
      ) : (
        <>
          <Text variant="body">
            Paid {formatMoney(totalPaid, currency)}
            {invoiceValue ? ` of ${formatMoney(invoiceValue, currency)}` : ''}
            {isPartial ? ' (partial)' : ''}
          </Text>
          {ratio !== null ? <ProgressBar progress={ratio} /> : null}
          {isPartial ? (
            <Text variant="small" muted>
              Showing {fetchedCount} of {totalCount} payments — total above covers only those shown.
            </Text>
          ) : null}

          {payments.length > 0 ? (
            <View style={styles.supplierPaymentList}>
              {payments.map((p) => (
                <View key={p.id} style={styles.supplierPaymentItem}>
                  <View style={styles.poHeaderRow}>
                    <Text variant="body">{formatMoney(p.amount, p.currency)}</Text>
                    <Text variant="small" muted>
                      {capitalize(p.payment_type)}
                    </Text>
                  </View>
                  <Text variant="small" muted>
                    {formatDate(p.payment_date)}
                    {p.swift_ref ? ` · ${p.swift_ref}` : ''}
                  </Text>
                  <DocumentsList entityType="payment" entityId={p.id} label="Supplier payment" />
                </View>
              ))}
            </View>
          ) : !isLoading ? (
            <Text variant="body" muted>
              No payments recorded.
            </Text>
          ) : null}
        </>
      )}

      <Button
        title="Record payment"
        variant="secondary"
        onPress={() =>
          router.push(`/bookings/${bookingId}/invoices/${invoiceId}/record-supplier-payment`)
        }
        style={styles.recordButton}
      />
    </View>
  );
}

function capitalize(s: string): string {
  return s.length === 0 ? s : s[0].toUpperCase() + s.slice(1);
}

function ClearingDocsSection({ docs }: { docs: ClearingDocs | null }) {
  if (!docs) return null;
  return (
    <Section title="Clearing docs">
      <Grid>
        <KV label="Status" value={docs.status} />
        <KV label="Customs entry ref" value={fmt(docs.customs_entry_ref)} />
        <KV label="HS code" value={fmt(docs.hs_code)} />
        <KV label="Duty rate" value={docs.duty_rate ? `${docs.duty_rate}%` : '—'} />
        <KV label="Estimated duty + VAT" value={formatMoney(docs.estimated_duty_vat, 'GBP')} />
      </Grid>
      <View style={styles.checksBlock}>
        <Check label="Customs entry" on={docs.has_customs_entry} />
        <Check label="Packing list" on={docs.has_packing_list} />
        <Check label="Cert. of origin" on={docs.has_certificate_of_origin} />
        <Check label="Health cert" on={docs.has_health_cert} />
      </View>
      <DocumentsList entityType="clearing_docs" entityId={docs.id} label="Clearing docs" />
    </Section>
  );
}

function Check({ label, on }: { label: string; on: boolean }) {
  return (
    <Text variant="small" style={on ? undefined : styles.checkOff}>
      {on ? '✓' : '○'} {label}
    </Text>
  );
}

function DeliverySection({ points }: { points: DeliveryPoint[] }) {
  if (points.length === 0) return null;
  return (
    <Section title={`Delivery points (${points.length})`}>
      {points.map((dp, i) => (
        <View
          key={dp.id}
          style={[styles.deliveryBlock, i < points.length - 1 && styles.dividerBottom]}
        >
          <View style={styles.poHeaderRow}>
            <Text variant="body">{dp.recipient_name}</Text>
            <Text variant="small" muted>
              {dp.status}
            </Text>
          </View>
          <Text variant="small" muted>
            {dp.address}
          </Text>
          <Grid>
            <KV label="Contact" value={dp.contact_name} />
            <KV label="Phone" value={dp.contact_phone} />
            <KV label="Broker" value={dp.broker?.name ?? '—'} />
            <KV label="End company" value={dp.end_company?.legal_name ?? '—'} />
            <KV label="Delivery type" value={fmt(dp.delivery_type)} />
            <KV label="Warehouse" value={fmt(dp.warehouse_name)} />
          </Grid>
          {dp.rebundled_at_warehouse ? (
            <Text variant="small" muted>
              Rebundled at warehouse
            </Text>
          ) : null}
          {dp.special_instructions ? (
            <View style={styles.notesInline}>
              <Text variant="small" muted>
                Instructions
              </Text>
              <Text variant="body">{dp.special_instructions}</Text>
            </View>
          ) : null}
          {dp.schedule ? <ScheduleBlock schedule={dp.schedule} /> : null}
        </View>
      ))}
    </Section>
  );
}

function ScheduleBlock({ schedule }: { schedule: NonNullable<DeliveryPoint['schedule']> }) {
  return (
    <View style={styles.scheduleBlock}>
      <View style={styles.poHeaderRow}>
        <Text variant="small" muted>
          Schedule
        </Text>
        <Text variant="small" muted>
          {schedule.status}
        </Text>
      </View>
      <Grid>
        <KV label="Date" value={formatDate(schedule.delivery_date)} />
        <KV label="Window" value={`${schedule.time_window_start}–${schedule.time_window_end}`} />
        <KV label="Haulier" value={schedule.haulier} />
        <KV label="Driver" value={fmt(schedule.driver_name)} />
        <KV label="Vehicle" value={fmt(schedule.vehicle_reg)} />
        <KV label="Delivered at" value={formatDateTime(schedule.delivered_at)} />
      </Grid>
      {schedule.failure_reason ? (
        <Text variant="small" style={styles.failureText}>
          Failure: {schedule.failure_reason}
        </Text>
      ) : null}
      {schedule.notes_to_recipient ? (
        <View style={styles.notesInline}>
          <Text variant="small" muted>
            Notes to recipient
          </Text>
          <Text variant="body">{schedule.notes_to_recipient}</Text>
        </View>
      ) : null}
      <DocumentsList
        entityType="delivery_schedule"
        entityId={schedule.id}
        label="Delivery schedule"
      />
    </View>
  );
}

function Section({
  title,
  right,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeaderRow}>
        <Text variant="heading">{title}</Text>
        {right}
      </View>
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

function fmt(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—';
  return String(value);
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
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sectionWide: {
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  sectionHeadingPadded: {
    paddingHorizontal: spacing.lg,
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
  poBlock: {
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  poHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  invoiceBlock: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    gap: spacing.sm,
  },
  supplierPaymentsBlock: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    gap: spacing.sm,
  },
  supplierPaymentList: {
    gap: spacing.sm,
  },
  supplierPaymentItem: {
    gap: spacing.xs,
  },
  recordButton: {
    marginTop: spacing.xs,
  },
  deliveryBlock: {
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  scheduleBlock: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    gap: spacing.sm,
  },
  dividerBottom: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  checksBlock: {
    marginTop: spacing.sm,
    gap: spacing.xs,
  },
  checkOff: {
    color: colors.textMuted,
  },
  notesInline: {
    gap: spacing.xs,
  },
  failureText: {
    color: colors.error,
  },
});
