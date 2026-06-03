import { Stack } from 'expo-router';
import React from 'react';

/**
 * Stack for the Admin tab (Phase 13a). The tab was a single "coming soon"
 * screen (`admin.tsx`); it's now a stack so the OPERATIONS sub-screens push
 * within the tab — mirroring the Bookings-tab stack. The section menu is
 * `index.tsx`; the three list screens push normally; the create/edit forms are
 * presented as modals (declared here, not via an in-component `<Stack.Screen>` —
 * `presentation` is fixed when the screen mounts). Names are relative to this
 * layout.
 *
 * The tab itself stays `name="admin"` in `(tabs)/_layout.tsx`, so the existing
 * `href: null` role-gating (admin-only) still applies unchanged.
 */
export default function AdminStackLayout() {
  return (
    <Stack>
      <Stack.Screen name="port-templates/[port]" options={{ presentation: 'modal' }} />
      <Stack.Screen name="brokers/new" options={{ presentation: 'modal' }} />
      <Stack.Screen name="end-customers/new" options={{ presentation: 'modal' }} />
    </Stack>
  );
}
