/**
 * Centered error message + retry button — the standard "this query failed"
 * affordance for full-screen / full-section read failures.
 *
 * Replaces an identical ~15-line copy that was pasted into five screens
 * (booking detail, container detail, bookings list, alerts, dashboard). It
 * unwraps the message with the usual ApiError → Error → fallback ladder, so an
 * `ApiError` shows the backend `detail`, any other `Error` shows its message,
 * and anything else shows a generic line. Use for read errors on non-modal
 * screens; modal forms use `<FormError>` instead (see Toasts in AGENTS.md).
 */

import React from 'react';
import { StyleSheet, View } from 'react-native';

import { ApiError } from '../../api/client';
import { spacing } from '../../theme/tokens';
import { Button } from './Button';
import { Text } from './Text';

export interface ErrorStateProps {
  /** The query/request error. */
  error: unknown;
  /** Called when the user taps Retry. */
  onRetry: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
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

const styles = StyleSheet.create({
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
