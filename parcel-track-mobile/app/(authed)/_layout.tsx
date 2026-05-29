import { Redirect, Stack } from 'expo-router';
import React from 'react';

import { useAuth } from '../../src/auth/AuthContext';
import { Spinner } from '../../src/components/ui';

export default function AuthedLayout() {
  const { status } = useAuth();

  if (status === 'loading') {
    return <Spinner centered />;
  }
  if (status !== 'authenticated') {
    return <Redirect href="/(auth)/login" />;
  }
  // Most routes register with default push presentation. The two container
  // form routes opt into modal presentation here (declaring it in the layout
  // is the reliable place — `presentation` is fixed when the screen mounts).
  return (
    <Stack>
      <Stack.Screen
        name="bookings/[id]/containers/[cid]/port-status"
        options={{ presentation: 'modal' }}
      />
      <Stack.Screen
        name="bookings/[id]/containers/[cid]/dispute"
        options={{ presentation: 'modal' }}
      />
    </Stack>
  );
}
