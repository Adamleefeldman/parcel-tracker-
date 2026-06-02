import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { ActivityIndicator, StyleSheet, TouchableOpacity, View } from 'react-native';

import { ApiError } from '../../api/client';
import { getDownloadUrl } from '../../api/documents/getDownloadUrl';
import { useDocuments } from '../../api/queries/useDocuments';
import type { DocumentEntityType } from '../../api/types/enums';
import type { DocumentListItem } from '../../api/types/document';
import { formatDate } from '../../lib/date';
import { formatBytes } from '../../lib/files';
import { colors, radii, spacing } from '../../theme/tokens';
import { Spinner, Text, useToast } from '../ui';

/**
 * Reusable documents affordance for one booking sub-entity, parameterized by
 * `(entityType, entityId, label)`. Wired into each sub-entity section on the
 * booking + container detail screens — one component, attached everywhere.
 *
 * Collapsed by default (a "Documents (N)" header) so the detail screens don't
 * bloat with always-open lists; tap the header to expand. Tapping a row mints a
 * fresh presigned GET URL and opens it in the system browser (lazy-imported —
 * no PDF renderer bundled). "Add" pushes the add-document modal.
 *
 * The booking id comes from the route (`/bookings/[id]/...`, which always wraps
 * this component) so callers only pass the entity-scoping props. Download
 * errors surface as a toast — this renders on a non-modal screen.
 */
export interface DocumentsListProps {
  entityType: DocumentEntityType;
  entityId: string;
  label: string;
}

export function DocumentsList({ entityType, entityId, label }: DocumentsListProps) {
  const router = useRouter();
  const { id: bookingId } = useLocalSearchParams<{ id: string }>();
  const { showToast } = useToast();
  const [expanded, setExpanded] = useState(false);
  const [openingId, setOpeningId] = useState<string | null>(null);

  const { data, isLoading, isError } = useDocuments(entityType, entityId);
  const documents = data?.items ?? [];
  const count = data?.total ?? documents.length;

  const onAdd = () => {
    router.push({
      pathname: '/bookings/[id]/add-document',
      params: { id: bookingId, entityType, entityId, label },
    });
  };

  const onOpen = async (docId: string) => {
    setOpeningId(docId);
    try {
      const url = await getDownloadUrl(docId);
      const WebBrowser = await import('expo-web-browser');
      await WebBrowser.openBrowserAsync(url);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Could not open the document.', 'error');
    } finally {
      setOpeningId(null);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <TouchableOpacity
          style={styles.headerLeft}
          onPress={() => setExpanded((v) => !v)}
          accessibilityRole="button"
        >
          <Text variant="small" muted>
            {expanded ? '▾' : '▸'} Documents ({count})
          </Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={onAdd} accessibilityRole="button">
          <Text variant="small" style={styles.add}>
            + Add
          </Text>
        </TouchableOpacity>
      </View>

      {expanded ? (
        isLoading ? (
          <Spinner />
        ) : isError ? (
          <Text variant="small" muted style={styles.body}>
            Couldn’t load documents.
          </Text>
        ) : documents.length === 0 ? (
          <Text variant="small" muted style={styles.body}>
            No documents.
          </Text>
        ) : (
          <View style={styles.list}>
            {documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                opening={openingId === doc.id}
                onPress={() => onOpen(doc.id)}
              />
            ))}
            {count > documents.length ? (
              <Text variant="small" muted style={styles.body}>
                Showing {documents.length} of {count}.
              </Text>
            ) : null}
          </View>
        )
      ) : null}
    </View>
  );
}

function DocumentRow({
  doc,
  opening,
  onPress,
}: {
  doc: DocumentListItem;
  opening: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity
      style={styles.row}
      onPress={onPress}
      disabled={opening}
      activeOpacity={0.7}
      accessibilityRole="button"
    >
      <View style={styles.rowText}>
        <Text variant="body" numberOfLines={1}>
          {doc.file_name}
        </Text>
        <Text variant="small" muted>
          {formatBytes(doc.file_size_bytes)} · {formatDate(doc.uploaded_at)}
        </Text>
      </View>
      {opening ? (
        <ActivityIndicator color={colors.primary} />
      ) : (
        <Text variant="body" muted>
          ↗
        </Text>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingTop: spacing.sm,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerLeft: {
    flex: 1,
    paddingVertical: spacing.xs,
  },
  add: {
    color: colors.primary,
    fontWeight: '600',
  },
  body: {
    marginTop: spacing.sm,
  },
  list: {
    marginTop: spacing.sm,
    gap: spacing.xs,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
  },
  rowText: {
    flex: 1,
    gap: spacing.xs,
  },
});
