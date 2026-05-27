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
  return <Stack />;
}
