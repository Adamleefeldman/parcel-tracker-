import { Stack } from 'expo-router';
import React from 'react';

/**
 * Anchor the Admin tab's stack to the section menu. Without this, state
 * restoration / a lingering modal can leave the tab showing a modal screen
 * (e.g. the port-template editor) instead of `index` when you tap the tab.
 * `initialRouteName` pins `index` as the stack's root so the tab always opens
 * on the menu and modals sit above it.
 */
export const unstable_settings = {
  initialRouteName: 'index',
};

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
      {/* Declare index first so it's unambiguously the stack root (belt-and-
          braces with unstable_settings.initialRouteName above). */}
      <Stack.Screen name="index" />
      {/* People (Phase 13b) */}
      <Stack.Screen name="users/index" />
      <Stack.Screen name="invites/index" />
      <Stack.Screen name="invites/new" options={{ presentation: 'modal' }} />
      {/* Operations (Phase 13a) */}
      <Stack.Screen name="port-templates/index" />
      <Stack.Screen name="brokers/index" />
      <Stack.Screen name="end-customers/index" />
      <Stack.Screen name="port-templates/edit" options={{ presentation: 'modal' }} />
      <Stack.Screen name="brokers/new" options={{ presentation: 'modal' }} />
      <Stack.Screen name="end-customers/new" options={{ presentation: 'modal' }} />
      {/* System (Phase 13b) */}
      <Stack.Screen name="audit-log/index" />
      <Stack.Screen name="system/push" />
      <Stack.Screen name="system/security" />
    </Stack>
  );
}
