import DateTimePicker, { type DateTimePickerEvent } from '@react-native-community/datetimepicker';
import React, { useState } from 'react';
import { Modal, Platform, Pressable, StyleSheet, TouchableOpacity, View } from 'react-native';

import { colors, overlays, radii, shadows, spacing } from '../../theme/tokens';
import { Button } from './Button';
import { Text } from './Text';

/**
 * Date picker field wrapping `@react-native-community/datetimepicker`. Value is
 * a `YYYY-MM-DD` string (the wire format); the native picker works in `Date`,
 * so we convert at the edges — anchoring parsed dates at local midday to avoid
 * a timezone off-by-one when round-tripping.
 *
 * Platform difference handled here: Android renders its own dialog (mount the
 * picker on demand, unmount on dismiss), while iOS has no built-in chrome — so
 * we host the inline picker in a bottom-sheet `Modal` with a Done button,
 * matching `Select`'s sheet pattern.
 */

export interface DateFieldProps {
  label?: string;
  /** Selected date as `YYYY-MM-DD`. Empty string renders the placeholder. */
  value: string;
  onChange: (value: string) => void;
  error?: string | null;
}

function isoToDate(iso: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12);
  return new Date();
}

function dateToIso(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function displayDate(iso: string): string {
  return isoToDate(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function DateField({ label, value, onChange, error }: DateFieldProps) {
  const [open, setOpen] = useState(false);
  const current = isoToDate(value);

  const onAndroidChange = (event: DateTimePickerEvent, selected?: Date) => {
    setOpen(false);
    if (event.type === 'set' && selected) onChange(dateToIso(selected));
  };

  const onIosChange = (_event: DateTimePickerEvent, selected?: Date) => {
    if (selected) onChange(dateToIso(selected));
  };

  return (
    <View style={styles.wrapper}>
      {label ? (
        <Text variant="small" muted style={styles.label}>
          {label}
        </Text>
      ) : null}
      <TouchableOpacity
        activeOpacity={0.7}
        style={[styles.field, error ? styles.fieldError : null]}
        onPress={() => setOpen(true)}
        accessibilityRole="button"
      >
        <Text variant="body" muted={!value}>
          {value ? displayDate(value) : 'Select date'}
        </Text>
      </TouchableOpacity>
      {error ? (
        <Text variant="small" style={styles.errorText}>
          {error}
        </Text>
      ) : null}

      {Platform.OS === 'android' && open ? (
        <DateTimePicker value={current} mode="date" display="default" onChange={onAndroidChange} />
      ) : null}

      {Platform.OS === 'ios' ? (
        <Modal
          visible={open}
          transparent
          animationType="fade"
          onRequestClose={() => setOpen(false)}
        >
          <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
            <Pressable style={styles.sheet} onPress={() => {}}>
              <DateTimePicker value={current} mode="date" display="inline" onChange={onIosChange} />
              <Button title="Done" onPress={() => setOpen(false)} />
            </Pressable>
          </Pressable>
        </Modal>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    marginBottom: spacing.md,
  },
  label: {
    marginBottom: spacing.xs,
  },
  field: {
    backgroundColor: colors.bgElev,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  fieldError: {
    borderColor: colors.red,
  },
  errorText: {
    color: colors.redInk,
    marginTop: spacing.xs,
  },
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: overlays.dim,
  },
  sheet: {
    backgroundColor: colors.bgElev,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
    ...shadows.sheet,
  },
});
