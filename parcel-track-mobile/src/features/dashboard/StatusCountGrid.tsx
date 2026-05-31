import React from 'react';
import { StyleSheet, TouchableOpacity, View } from 'react-native';

import type { BookingStatus } from '../../api/types/enums';
import { Card, Text } from '../../components/ui';
import { humanizeStatus } from '../../components/ui/statusPillMapping';
import { spacing } from '../../theme/tokens';
import type { StatusCounts } from '../../lib/bookingStatusCounts';

export interface StatusCountGridProps {
  statuses: BookingStatus[];
  counts: StatusCounts;
  onSelect?: (status: BookingStatus) => void;
}

/** A wrap of count cards — one per emphasized status. Cosmetic only. */
export function StatusCountGrid({ statuses, counts, onSelect }: StatusCountGridProps) {
  return (
    <View style={styles.grid}>
      {statuses.map((status) => (
        <TouchableOpacity
          key={status}
          style={styles.cell}
          activeOpacity={0.7}
          disabled={!onSelect}
          onPress={() => onSelect?.(status)}
        >
          <Card style={styles.card}>
            <Text variant="display">{counts[status]}</Text>
            <Text variant="small" muted numberOfLines={2}>
              {humanizeStatus(status)}
            </Text>
          </Card>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  cell: {
    flexBasis: '31%',
    flexGrow: 1,
  },
  card: {
    gap: spacing.xs,
  },
});
