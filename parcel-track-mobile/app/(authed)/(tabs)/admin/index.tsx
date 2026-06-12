import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { useRouter } from 'expo-router';
import React from 'react';
import { ScrollView, StyleSheet, TouchableOpacity, View } from 'react-native';

import { useAuth } from '@/src/auth/AuthContext';
import { Card, IconBox, ScreenContainer, Text } from '@/src/components/ui';
import { colors, spacing } from '@/src/theme/tokens';

/**
 * Admin console section menu. Renders the prototype's three sections — PEOPLE /
 * OPERATIONS / SYSTEM — all now live. PEOPLE (Invites, Users) and SYSTEM (Audit
 * log, Push notifications, Security) landed in Phase 13b on the new admin read
 * endpoints (`GET /users`/`/invites`/`/audit-logs`) plus the existing
 * `POST /auth/invite` for sends; OPERATIONS (port templates / brokers / end
 * customers) landed in Phase 13a. Scope is view + send-invites — no
 * revoke/deactivate/role-change; Push + Security are static info panels.
 *
 * The tab is hidden for non-admins (`href: null` in the tabs layout); a
 * deep-linked non-admin gets a friendly "not available" body here, and each
 * sub-screen re-checks (defense-in-depth; the server is the real gate).
 */
type AdminRow = {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle: string;
  /** Navigation target for the row. */
  href: string;
};

const SECTIONS: { heading: string; rows: AdminRow[] }[] = [
  {
    heading: 'People',
    rows: [
      {
        icon: 'person-add-outline',
        title: 'Invites',
        subtitle: 'Invite agents & customers',
        href: '/admin/invites',
      },
      {
        icon: 'people-outline',
        title: 'Users',
        subtitle: 'Roles & access',
        href: '/admin/users',
      },
    ],
  },
  {
    heading: 'Operations',
    rows: [
      {
        icon: 'boat-outline',
        title: 'Port templates',
        subtitle: 'Free-day defaults · rate cards',
        href: '/admin/port-templates',
      },
      {
        icon: 'cube-outline',
        title: 'Brokers',
        subtitle: 'UK & Morocco brokers',
        href: '/admin/brokers',
      },
      {
        icon: 'business-outline',
        title: 'End customers',
        subtitle: 'Aliases · registration · VAT',
        href: '/admin/end-customers',
      },
    ],
  },
  {
    heading: 'System',
    rows: [
      {
        icon: 'document-text-outline',
        title: 'Audit log',
        subtitle: 'Append-only state history',
        href: '/admin/audit-log',
      },
      {
        icon: 'notifications-outline',
        title: 'Push notifications',
        subtitle: 'Delivery & templates',
        href: '/admin/system/push',
      },
      {
        icon: 'shield-checkmark-outline',
        title: 'Security',
        subtitle: 'JWT · revocation · bcrypt',
        href: '/admin/system/security',
      },
    ],
  },
];

export default function AdminScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const version = Constants.expoConfig?.version;

  if (user?.role !== 'admin') {
    return (
      <ScreenContainer padded={false}>
        <View style={styles.header}>
          <Text variant="display">Admin</Text>
        </View>
        <View style={styles.centered}>
          <Text muted style={styles.centeredText}>
            The admin console isn&apos;t available for your role.
          </Text>
        </View>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer padded={false}>
      <View style={styles.header}>
        <Text variant="display">Admin</Text>
        <Text variant="small" muted>
          WT Trading · The FMCG Hub
        </Text>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {SECTIONS.map((section) => (
          <View key={section.heading} style={styles.section}>
            <Text variant="overline" muted style={styles.sectionHeading}>
              {section.heading}
            </Text>
            {section.rows.map((row) => (
              <TouchableOpacity
                key={row.title}
                activeOpacity={0.7}
                onPress={() => router.push(row.href as never)}
              >
                <Card style={styles.row}>
                  <IconBox icon={row.icon} />
                  <View style={styles.rowBody}>
                    <Text variant="title">{row.title}</Text>
                    <Text variant="small" muted>
                      {row.subtitle}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={colors.ink4} />
                </Card>
              </TouchableOpacity>
            ))}
          </View>
        ))}

        <Text variant="small" muted mono style={styles.footer}>
          The FMCG Hub{version ? ` · v${version}` : ''}
        </Text>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    gap: spacing.xs,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.lg,
  },
  section: {
    gap: spacing.sm,
  },
  sectionHeading: {
    paddingLeft: spacing.xs,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  rowBody: {
    flex: 1,
    gap: spacing.xs,
  },
  footer: {
    textAlign: 'center',
    paddingTop: spacing.md,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  centeredText: {
    textAlign: 'center',
  },
});
