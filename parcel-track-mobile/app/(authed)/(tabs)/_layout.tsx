import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import React from 'react';

import { canSeeMoneyRisk } from '@/src/api/queries/useMoneyRisk';
import { useUnreadCount } from '@/src/api/queries/useUnreadCount';
import { useAuth } from '@/src/auth/AuthContext';
import { colors } from '@/src/theme/tokens';

/**
 * Bottom-tab navigator — the four top-level destinations (Phase 10 IA), shown
 * role-aware. The labels are counterintuitive, so spell them out:
 *
 *  - **Bookings** — the landing tab. A stack (`bookings/_layout.tsx`) whose list
 *    screen also carries the merged "Today" dashboard header + money hero cards.
 *  - **Alerts** — the **Money-risk** dashboard (`money-risk.tsx`), NOT
 *    notifications. Admin + uk_agent only.
 *  - **Inbox** — the **notifications** feed (`inbox.tsx`). The unread badge is
 *    here now (moved off the old Alerts tab).
 *  - **Admin** — the admin console shell (`admin.tsx`). Admin only.
 *
 * **Cold start lands on Bookings** via a hidden `index` redirect route
 * (`index.tsx` → `<Redirect href="/bookings" />`). The tab group needs a screen
 * for its base path; without one, route resolution fails at startup and the
 * splash freezes (the root hides the splash in a post-commit effect). The
 * redirect resolves the base path and forwards to Bookings — more robust than an
 * `initialRouteName` with no index route.
 *
 * Role gating is cosmetic (`href: null` hides a tab); the server is the real
 * gate. Money-risk is additionally `enabled`-gated in its query so a hidden-tab
 * role never fires a 403.
 */
export default function TabsLayout() {
  const { user } = useAuth();
  const role = user?.role;
  const { data: unread } = useUnreadCount();
  const badge = unread && unread > 0 ? (unread > 99 ? '99+' : unread) : undefined;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
      }}
    >
      {/* Base-path redirect → Bookings. Hidden from the tab bar; exists only so
          the group's base path resolves (see the header comment). */}
      <Tabs.Screen name="index" options={{ href: null }} />
      <Tabs.Screen
        name="bookings"
        options={{
          title: 'Bookings',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="cube-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="money-risk"
        options={{
          title: 'Alerts',
          // Hidden for roles the endpoint 403s (morocco_agent / customer).
          href: canSeeMoneyRisk(role) ? undefined : null,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="notifications-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="inbox"
        options={{
          title: 'Inbox',
          tabBarBadge: badge,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="file-tray-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="admin"
        options={{
          title: 'Admin',
          href: role === 'admin' ? undefined : null,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="settings-outline" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
