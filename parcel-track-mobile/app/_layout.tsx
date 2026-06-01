/**
 * Root layout.
 *
 * Wires the three providers every screen depends on:
 *   - QueryClientProvider (server state)
 *   - SafeAreaProvider    (insets for `<ScreenContainer>`)
 *   - AuthProvider        (status + user)
 *
 * Everything below this point is a route group. `(auth)` and `(authed)`
 * each have a `_layout.tsx` that handles its own redirect guard.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Slot, type ErrorBoundaryProps } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '../src/auth/AuthContext';
import { Button, ScreenContainer, Text, ToastProvider } from '../src/components/ui';
import { spacing } from '../src/theme/tokens';

export default function RootLayout() {
  // useState keeps the QueryClient stable across re-renders (no `new` on every render).
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <AuthProvider>
          <ToastProvider>
            <Slot />
            <StatusBar style="auto" />
          </ToastProvider>
        </AuthProvider>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}

/**
 * Root error boundary. Expo Router renders a route's exported `ErrorBoundary`
 * (this is its per-route boundary API) in place of the subtree when a render
 * throws. Exported from the *root* layout, it's the app-wide safety net — any
 * uncaught render error shows a friendly fallback with a retry instead of a
 * white screen (Hermes has no dev red-box in a release build).
 *
 * `retry()` (from the boundary props) re-mounts the failed subtree; for a
 * transient error (e.g. a malformed-data render that's since been refetched)
 * this recovers in place without a full app restart.
 */
export function ErrorBoundary({ retry }: ErrorBoundaryProps) {
  return (
    <ScreenContainer>
      <View style={styles.boundary}>
        <Text variant="heading" style={styles.boundaryText}>
          Something went wrong
        </Text>
        <Text variant="body" muted style={styles.boundaryText}>
          The screen ran into an unexpected error. You can try again.
        </Text>
        <Button title="Try again" onPress={() => retry()} />
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  boundary: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
  },
  boundaryText: {
    textAlign: 'center',
  },
});
