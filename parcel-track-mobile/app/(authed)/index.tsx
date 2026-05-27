import { Redirect } from 'expo-router';
import React from 'react';

// Home for authenticated users currently is just the bookings list.
// Replace with a real dashboard once there is one.
export default function AuthedIndex() {
  return <Redirect href="/(authed)/bookings" />;
}
