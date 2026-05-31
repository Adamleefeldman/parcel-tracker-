import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import React from 'react';

import { useUnreadCount } from '@/src/api/queries/useUnreadCount';
import { colors } from '@/src/theme/tokens';

/**
 * Bottom tab navigator — the three top-level destinations for a signed-in
 * user. The Bookings tab is itself a stack (`bookings/_layout.tsx`) so its
 * list → detail → container → modal flow lives entirely inside the tab.
 *
 * The Alerts tab shows an unread badge. There is no `/notifications/unread-count`
 * endpoint, so `useUnreadCount` derives it from the list's `total` with
 * `unread_only=true&limit=1` (see the hook).
 */
export default function TabsLayout() {
  const { data: unread } = useUnreadCount();
  const badge = unread && unread > 0 ? (unread > 99 ? '99+' : unread) : undefined;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Dashboard',
          tabBarIcon: ({ color, size }) => <Ionicons name="home-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="bookings"
        options={{
          title: 'Bookings',
          tabBarIcon: ({ color, size }) => <Ionicons name="cube-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="alerts"
        options={{
          title: 'Alerts',
          tabBarBadge: badge,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="notifications-outline" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
