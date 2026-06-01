import { Redirect, Stack } from 'expo-router';
import React from 'react';

import { useAuth } from '@/src/auth/AuthContext';
import { Spinner } from '@/src/components/ui';

// Authed-area guard. The signed-in experience is a bottom-tab navigator
// (`(tabs)`): Dashboard | Bookings | Alerts. Modal routes (port-status,
// dispute, record-payment) are registered inside the Bookings tab's own stack
// (`(tabs)/bookings/_layout.tsx`), not here. This Stack only needs the guard;
// `headerShown: false` because the Tabs navigator and the per-tab stacks own
// their own headers.
export default function AuthedLayout() {
  const { status } = useAuth();

  if (status === 'loading') {
    return <Spinner centered />;
  }
  if (status !== 'authenticated') {
    return <Redirect href="/(auth)/login" />;
  }
  return <Stack screenOptions={{ headerShown: false }} />;
}
