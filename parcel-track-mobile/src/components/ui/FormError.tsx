/**
 * Inline error banner for modal form screens.
 *
 * Why not just a toast? The global `<ToastProvider>` renders at the app root,
 * but Expo Router's `presentation: 'modal'` screens are presented in a native
 * layer *above* the root — so a toast fired while a modal is open is drawn
 * behind it and never seen. Mutation errors on a form deliberately keep the
 * user on the form (to fix + retry), so the feedback has to live on the form.
 * Use this for in-modal mutation errors; use `useToast` for feedback on a
 * normal (non-modal) screen, or for success right before `router.back()`.
 */

import React from 'react';
import { StyleSheet, View } from 'react-native';

import { ApiError } from '../../api/client';
import { colors, radii, spacing } from '../../theme/tokens';
import { Text } from './Text';

export interface FormErrorProps {
  /** The mutation/request error, or null/undefined when there's nothing to show. */
  error: unknown;
  /** Shown when `error` isn't an ApiError with a usable message. */
  fallback: string;
}

export function FormError({ error, fallback }: FormErrorProps) {
  if (!error) return null;
  const message = error instanceof ApiError ? error.message : fallback;
  return (
    <View style={styles.banner}>
      <Text variant="label" color={colors.redInk}>
        {message}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.redSoft,
    borderRadius: radii.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.md,
  },
});
