import { Stack } from 'expo-router';
import React from 'react';

/**
 * Stack for the Bookings tab: list → detail → container detail, plus the three
 * container form routes presented as modals. Declaring `presentation: 'modal'`
 * here (not via an in-component `<Stack.Screen>`) is the reliable place — the
 * presentation is fixed when the screen mounts. Names are relative to this
 * layout, so the `bookings/` prefix from the old `(authed)/_layout.tsx`
 * registration is dropped.
 */
export default function BookingsStackLayout() {
  return (
    <Stack>
      <Stack.Screen
        name="[id]/containers/[cid]/port-status"
        options={{ presentation: 'modal' }}
      />
      <Stack.Screen name="[id]/containers/[cid]/dispute" options={{ presentation: 'modal' }} />
      <Stack.Screen
        name="[id]/containers/[cid]/record-payment"
        options={{ presentation: 'modal' }}
      />
      <Stack.Screen name="[id]/add-document" options={{ presentation: 'modal' }} />
      <Stack.Screen
        name="[id]/invoices/[invoiceId]/record-supplier-payment"
        options={{ presentation: 'modal' }}
      />
    </Stack>
  );
}
