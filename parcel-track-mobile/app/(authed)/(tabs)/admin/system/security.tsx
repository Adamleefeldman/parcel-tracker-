import { Ionicons } from '@expo/vector-icons';
import { Stack } from 'expo-router';
import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import { Card, IconBox, ScreenContainer, Text } from '@/src/components/ui';
import { spacing } from '@/src/theme/tokens';

/**
 * Static informational panel (Admin → System → Security). Describes how the
 * backend secures the API — JWT access/refresh, Redis-backed token revocation,
 * bcrypt password hashing. Informational only: no fetch, no editable config.
 */
type SecurityItem = {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  detail: string;
};

const ITEMS: SecurityItem[] = [
  {
    icon: 'key-outline',
    title: 'JWT access + refresh',
    detail:
      'Short-lived access tokens with a refresh-token rotation flow. The app stores both in the device secure store only.',
  },
  {
    icon: 'refresh-outline',
    title: 'Redis token revocation',
    detail:
      'Logout and compromised tokens are revoked server-side via a Redis denylist — a stolen token can be cut off before it expires.',
  },
  {
    icon: 'lock-closed-outline',
    title: 'bcrypt password hashing',
    detail:
      'Passwords are hashed with bcrypt; the API never stores or returns a plaintext password.',
  },
];

export default function SecurityScreen() {
  const { user } = useAuth();

  if (!canManageAdmin(user?.role as UserRole | undefined)) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Security' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to view this.
        </Text>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer padded={false}>
      <Stack.Screen options={{ title: 'Security' }} />
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text variant="small" muted style={styles.intro}>
          How the backend protects accounts and sessions. These settings are managed server-side and
          aren&apos;t configurable from the app.
        </Text>

        {ITEMS.map((item) => (
          <Card key={item.title} style={styles.card}>
            <IconBox icon={item.icon} />
            <View style={styles.cardBody}>
              <Text variant="title">{item.title}</Text>
              <Text variant="small" muted style={styles.detail}>
                {item.detail}
              </Text>
            </View>
          </Card>
        ))}
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
  },
  intro: {
    lineHeight: 18,
  },
  card: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  cardBody: {
    flex: 1,
    gap: spacing.xs,
  },
  detail: {
    lineHeight: 18,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
