import { Redirect, Stack } from 'expo-router';
import React from 'react';

import { Spinner } from '../../src/components/ui';
import { useAuth } from '../../src/auth/AuthContext';

export default function AuthLayout() {
  const { status } = useAuth();

  if (status === 'loading') {
    return <Spinner centered />;
  }
  if (status === 'authenticated') {
    return <Redirect href="/(authed)" />;
  }
  return <Stack screenOptions={{ headerShown: false }} />;
}
