import { Redirect } from 'expo-router';
import React from 'react';

/**
 * Default-route redirect for the tab group.
 *
 * The signed-in landing is the **Bookings** tab, but a tab navigator still needs
 * a screen for the group's base path (`/` → `(authed)/(tabs)`). Without one,
 * expo-router has nothing to render for that path and route resolution fails at
 * startup — which, because the root only hides the splash in a post-commit
 * effect, manifests as a frozen splash. So this `index` route exists purely to
 * resolve the base path and immediately redirect to `/bookings`. It's hidden
 * from the tab bar (`href: null` in `_layout.tsx`).
 */
export default function TabsIndexRedirect() {
  return <Redirect href="/bookings" />;
}
