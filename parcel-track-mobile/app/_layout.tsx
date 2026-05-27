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
import { Slot } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '../src/auth/AuthContext';

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
          <Slot />
          <StatusBar style="auto" />
        </AuthProvider>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
