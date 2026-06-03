import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { useRouter } from 'expo-router';
import React from 'react';
import { ScrollView, StyleSheet, TouchableOpacity, View } from 'react-native';

import { useAuth } from '@/src/auth/AuthContext';
import { Card, Pill, ScreenContainer, Text } from '@/src/components/ui';
import { colors, spacing } from '@/src/theme/tokens';

/**
 * Admin console section menu (Phase 13a). Renders the prototype's three
 * sections — PEOPLE / OPERATIONS / SYSTEM. **OPERATIONS is now live**: its rows
 * navigate into the port-templates / brokers / end-customers screens (all on
 * existing admin-gated backend APIs). PEOPLE (invites/users) and SYSTEM (audit
 * log / push / security) stay non-interactive "coming soon" rows — Phase 13b,
 * which likely needs new backend (invite/user management + an audit read API).
 *
 * The tab is hidden for non-admins (`href: null` in the tabs layout); a
 * deep-linked non-admin gets a friendly "not available" body (defense-in-depth;
 * the server is the real gate for every admin endpoint).
 */
type AdminRow = {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle: string;
  /** When set, the row navigates here; otherwise it's a "coming soon" row. */
  href?: string;
};

const SECTIONS: { heading: string; rows: AdminRow[] }[] = [
  {
    heading: 'People',
    rows: [
      { icon: 'person-add-outline', title: 'Invites', subtitle: 'Invite agents & customers' },
      { icon: 'people-outline', title: 'Users', subtitle: 'Roles & access' },
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
      { icon: 'document-text-outline', title: 'Audit log', subtitle: 'Append-only state history' },
      {
        icon: 'notifications-outline',
        title: 'Push notifications',
        subtitle: 'Delivery & templates',
      },
      {
        icon: 'shield-checkmark-outline',
        title: 'Security',
        subtitle: 'JWT · revocation · bcrypt',
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
            {section.rows.map((row) => {
              const body = (
                <Card style={styles.row}>
                  <View style={styles.iconWrap}>
                    <Ionicons name={row.icon} size={20} color={colors.ink2} />
                  </View>
                  <View style={styles.rowBody}>
                    <Text variant="title">{row.title}</Text>
                    <Text variant="small" muted>
                      {row.subtitle}
                    </Text>
                  </View>
                  {row.href ? (
                    <Text variant="body" muted style={styles.chevron}>
                      ›
                    </Text>
                  ) : (
                    <Pill tone="default">Soon</Pill>
                  )}
                </Card>
              );

              if (!row.href) {
                return <View key={row.title}>{body}</View>;
              }
              return (
                <TouchableOpacity
                  key={row.title}
                  activeOpacity={0.7}
                  onPress={() => router.push(row.href as never)}
                >
                  {body}
                </TouchableOpacity>
              );
            })}
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
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.bgSoft,
  },
  rowBody: {
    flex: 1,
    gap: 2,
  },
  chevron: {
    fontSize: 22,
    lineHeight: 22,
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
