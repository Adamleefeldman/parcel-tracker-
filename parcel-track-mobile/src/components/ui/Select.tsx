import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Modal, Pressable, StyleSheet, TouchableOpacity, View } from 'react-native';

import { colors, overlays, radii, shadows, spacing } from '../../theme/tokens';
import { ListItem } from './ListItem';
import { Text } from './Text';

/**
 * Modal-based dropdown. Built entirely on RN `Modal` + existing primitives —
 * no `@react-native-picker/picker` dependency. The library would give native
 * wheel/dropdown UX but brings platform quirks and another native module to
 * pin against the Expo SDK; for a short option list a tap-to-open sheet of
 * `ListItem`s is simpler to control and looks consistent across iOS/Android.
 * Reach for the picker only if richer native behaviour (long lists, search)
 * is ever needed.
 */

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  value: string | null;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  /**
   * Block opening the sheet (e.g. while the pre-fill query is still loading —
   * pair with a "Loading…" placeholder so the field doesn't blank-then-pop).
   */
  disabled?: boolean;
}

export function Select({ value, options, onChange, placeholder, label, disabled }: SelectProps) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);

  return (
    <View style={styles.wrapper}>
      {label ? (
        <Text variant="small" muted style={styles.label}>
          {label}
        </Text>
      ) : null}
      <TouchableOpacity
        activeOpacity={0.7}
        style={[styles.field, disabled && styles.fieldDisabled]}
        onPress={() => setOpen(true)}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityState={{ disabled: !!disabled }}
      >
        <Text variant="body" muted={!selected}>
          {selected ? selected.label : (placeholder ?? 'Select…')}
        </Text>
        <Ionicons name="chevron-down" size={18} color={colors.ink4} style={styles.caret} />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          {/* Stop taps inside the sheet from dismissing it. */}
          <Pressable style={styles.sheet} onPress={() => {}}>
            {label ? (
              <Text variant="heading" style={styles.sheetTitle}>
                {label}
              </Text>
            ) : null}
            {options.map((option) => (
              <ListItem
                key={option.value}
                title={option.label}
                right={
                  option.value === value ? (
                    <Text variant="body" style={styles.check}>
                      ✓
                    </Text>
                  ) : undefined
                }
                onPress={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              />
            ))}
          </Pressable>
        </Pressable>
      </Modal>
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
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.bgElev,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  fieldDisabled: {
    backgroundColor: colors.bgSoft,
  },
  caret: {
    marginLeft: spacing.sm,
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
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxl,
    ...shadows.sheet,
  },
  sheetTitle: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  check: {
    color: colors.primary,
  },
});
