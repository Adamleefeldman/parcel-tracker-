import React from 'react';
import { StyleSheet, TouchableOpacity, View } from 'react-native';

import type { Booking } from '../../api/queries/useBookings';
import type { BookingStatus } from '../../api/types/enums';
import { Card, StatusPill, Text } from '../../components/ui';
import { humanizeStatus } from '../../components/ui/statusPillMapping';
import { formatDate } from '../../lib/date';
import { colors, radii, sizes, spacing } from '../../theme/tokens';
import { BOOKING_STAGES, bookingStageIndex } from './bookingProgress';

/**
 * Rich booking card for the bookings list — the prototype's card language:
 * mono ref + status pill, route/ETA line, goods line, counts·vessel meta line,
 * and a compact segmented progress bar driven by the shared
 * `bookingProgress` mapping (same model as `BookingStepper`, micro height).
 *
 * The summary fields (`po_count`…`product_summary`) come from the paired
 * backend list-enrichment PR and are all optional — against an un-enriched
 * backend the card degrades to ref + pill + created date + progress, which the
 * layout treats as the no-summary case, not an error.
 */
export interface BookingCardProps {
  booking: Booking;
  onPress: (id: string) => void;
}

export function BookingCard({ booking, onPress }: BookingCardProps) {
  const status = booking.status as BookingStatus;
  const stageIndex = bookingStageIndex(status);

  const routeParts: string[] = [];
  if (booking.port_of_discharge) routeParts.push(humanizeStatus(booking.port_of_discharge));
  if (booking.eta) routeParts.push(`ETA ${formatDate(booking.eta)}`);
  const subtitle =
    routeParts.length > 0 ? routeParts.join(' · ') : `Created ${formatDate(booking.created_at)}`;

  const metaParts: string[] = [];
  if (booking.po_count != null) {
    metaParts.push(`${booking.po_count} ${booking.po_count === 1 ? 'PO' : 'POs'}`);
  }
  if (booking.container_count != null) {
    metaParts.push(
      `${booking.container_count} ${booking.container_count === 1 ? 'container' : 'containers'}`,
    );
  }
  if (booking.vessel_name) metaParts.push(`M/V ${booking.vessel_name}`);
  const meta = metaParts.join(' · ');
  const goods = booking.product_summary ?? '';

  return (
    <TouchableOpacity activeOpacity={0.7} onPress={() => onPress(booking.id)}>
      <Card style={styles.card}>
        <View style={styles.headerRow}>
          <Text variant="title" mono numberOfLines={1} style={styles.ref}>
            {booking.booking_number || booking.reference}
          </Text>
          <StatusPill kind="booking" status={status} />
        </View>
        <Text variant="small" muted numberOfLines={1}>
          {subtitle}
        </Text>

        {goods || meta ? (
          <View style={styles.summaryBlock}>
            <View style={styles.divider} />
            {goods ? (
              <Text variant="body" numberOfLines={1}>
                {goods}
              </Text>
            ) : null}
            {meta ? (
              <Text variant="small" muted numberOfLines={1}>
                {meta}
              </Text>
            ) : null}
          </View>
        ) : null}

        <View style={styles.track}>
          {BOOKING_STAGES.map((stage, i) => (
            <View
              key={stage}
              style={[styles.segment, i <= stageIndex ? styles.segmentOn : styles.segmentOff]}
            />
          ))}
        </View>
      </Card>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.xs,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  ref: {
    flexShrink: 1,
  },
  summaryBlock: {
    gap: spacing.xs,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.line,
    marginVertical: spacing.xs,
  },
  track: {
    flexDirection: 'row',
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  segment: {
    flex: 1,
    height: sizes.trackMicro,
    borderRadius: radii.pill,
  },
  segmentOn: {
    backgroundColor: colors.primary,
  },
  segmentOff: {
    backgroundColor: colors.bgSunk,
  },
});
