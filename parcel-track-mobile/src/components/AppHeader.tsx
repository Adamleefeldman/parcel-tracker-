import React from 'react';
import { StyleSheet, View } from 'react-native';

import { useAuth } from '../auth/AuthContext';
import { Pill, Text } from './ui';
import { spacing } from '../theme/tokens';
import type { UserRole } from '../api/types/enums';

/**
 * Header label used on detail screens. Renders the screen title plus a small
 * chip showing the current user's role — a UI hint so an admin and a customer
 * can tell them apart at a glance. Authorization is server-enforced; this is
 * cosmetic only.
 */

const ROLE_LABEL: Record<UserRole | (string & {}), string> = {
  admin: 'Admin',
  morocco_agent: 'Morocco',
  uk_agent: 'UK',
  customer: 'Customer',
};

export function AppHeader({ title }: { title: string }) {
  const { user } = useAuth();
  const roleLabel = user ? (ROLE_LABEL[user.role] ?? user.role) : null;
  return (
    <View style={styles.row}>
      <Text variant="heading" numberOfLines={1}>
        {title}
      </Text>
      {roleLabel ? <Pill tone="default">{roleLabel}</Pill> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
});
