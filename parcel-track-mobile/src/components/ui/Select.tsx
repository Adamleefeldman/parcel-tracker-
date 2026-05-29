import React, { useState } from 'react';
import { Modal, Pressable, StyleSheet, TouchableOpacity, View } from 'react-native';

import { colors, radii, spacing, type as typo } from '../../theme/tokens';
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
}

export function Select({ value, options, onChange, placeholder, label }: SelectProps) {
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
        style={styles.field}
        onPress={() => setOpen(true)}
        accessibilityRole="button"
      >
        <Text variant="body" muted={!selected}>
          {selected ? selected.label : (placeholder ?? 'Select…')}
        </Text>
        <Text variant="body" muted style={styles.caret}>
          ⌄
        </Text>
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
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  caret: {
    ...typo.body,
    marginLeft: spacing.sm,
  },
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  sheet: {
    backgroundColor: colors.bg,
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  sheetTitle: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  check: {
    color: colors.primary,
  },
});
