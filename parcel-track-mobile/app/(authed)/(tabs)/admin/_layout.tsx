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
 *
 * Note the port-template editor is a **static** `port-templates/edit` route that
 * takes the port as a query param, NOT a dynamic `port-templates/[port]`:
 * expo-router doesn't reliably bind a modal screen's own terminal dynamic
 * segment to `useLocalSearchParams`, so a query param is used instead.
 */
export default function AdminStackLayout() {
  return (
    <Stack>
      <Stack.Screen name="port-templates/edit" options={{ presentation: 'modal' }} />
      <Stack.Screen name="brokers/new" options={{ presentation: 'modal' }} />
      <Stack.Screen name="end-customers/new" options={{ presentation: 'modal' }} />
    </Stack>
  );
}
