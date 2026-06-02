import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useUploadDocument, type UploadPhase } from '@/src/api/mutations/useUploadDocument';
import type { DocumentEntityType } from '@/src/api/types/enums';
import {
  Button,
  FormError,
  ProgressBar,
  ScreenContainer,
  Spinner,
  Text,
  useToast,
} from '@/src/components/ui';
import { formatBytes, validateFile } from '@/src/lib/files';
import { colors, radii, spacing } from '@/src/theme/tokens';

/**
 * Add-document modal. Reached from any `<DocumentsList>` "Add" button with the
 * sub-entity scope in the query string (`entityType`, `entityId`, `label`) plus
 * the booking `id` (for the route path). Drives the local flow
 * idle → selected → uploading(%) → error; the upload mutation owns the
 * presign → PUT → confirm round-trip.
 *
 * Picker modules are lazy-imported in the handlers (bundle hygiene — they pull
 * native code most screens never touch). Errors stay inline via `<FormError>`
 * because a toast would paint behind this modal; success toasts on the screen
 * behind after `router.back()`.
 */
interface SelectedFile {
  fileUri: string;
  fileName: string;
  contentType: string;
  fileSize?: number;
}

export default function AddDocumentScreen() {
  const router = useRouter();
  const { entityType, entityId, label } = useLocalSearchParams<{
    entityType: DocumentEntityType;
    entityId: string;
    label?: string;
  }>();
  const { showToast } = useToast();
  const mutation = useUploadDocument(entityType, entityId);

  const [selected, setSelected] = useState<SelectedFile | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState<UploadPhase | null>(null);
  // Some Android providers report no total byte count, so the PUT never emits a
  // progress event and the bar would sit at 0. Track whether any event arrived;
  // until one does (and during the no-progress confirm step) we show an
  // indeterminate spinner instead of a stuck bar.
  const [progressSeen, setProgressSeen] = useState(false);

  const applySelection = (file: SelectedFile) => {
    setValidationError(validateFile({ size: file.fileSize, contentType: file.contentType }));
    setSelected(file);
    setProgress(0);
    setPhase(null);
    setProgressSeen(false);
    mutation.reset();
  };

  const onPickDocument = async () => {
    const DocumentPicker = await import('expo-document-picker');
    const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    applySelection({
      fileUri: asset.uri,
      fileName: asset.name,
      contentType: asset.mimeType ?? 'application/octet-stream',
      fileSize: asset.size,
    });
  };

  const onPickImage = async (source: 'camera' | 'library') => {
    const ImagePicker = await import('expo-image-picker');
    const permission =
      source === 'camera'
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setSelected(null);
      setValidationError(
        source === 'camera'
          ? 'Camera permission is needed to take a photo.'
          : 'Photo-library permission is needed to choose a photo.',
      );
      return;
    }
    const result =
      source === 'camera'
        ? await ImagePicker.launchCameraAsync({ quality: 1 })
        : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1 });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    // The image picker may omit name/mime — derive a sensible default so the
    // Content-Type we present at presign is one R2 will accept.
    const contentType = asset.mimeType ?? 'image/jpeg';
    const fileName = asset.fileName ?? deriveImageName(asset.uri, contentType);
    applySelection({ fileUri: asset.uri, fileName, contentType, fileSize: asset.fileSize });
  };

  const onUpload = () => {
    if (!selected || validationError) return;
    setProgress(0);
    setPhase(null);
    setProgressSeen(false);
    mutation.mutate(
      {
        fileUri: selected.fileUri,
        fileName: selected.fileName,
        contentType: selected.contentType,
        fileSize: selected.fileSize,
        onProgress: (fraction) => {
          setProgressSeen(true);
          setProgress(fraction);
        },
        onPhase: setPhase,
      },
      {
        onSuccess: () => {
          showToast('Document uploaded', 'success');
          router.back();
        },
      },
    );
  };

  const uploading = mutation.isPending;
  const title = label ? `Add to ${label}` : 'Add document';

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title: 'Add document' }} />
      <View style={styles.body}>
        <Text variant="heading">{title}</Text>

        {!selected ? (
          <Text variant="body" muted>
            Choose a PDF, image, or spreadsheet (up to 50 MB).
          </Text>
        ) : (
          <View style={styles.selectedBlock}>
            <Text variant="body" numberOfLines={2}>
              {selected.fileName}
            </Text>
            <Text variant="small" muted>
              {selected.contentType}
              {selected.fileSize != null ? ` · ${formatBytes(selected.fileSize)}` : ''}
            </Text>
          </View>
        )}

        <View style={styles.pickers}>
          <Button
            title="Choose file"
            variant="secondary"
            onPress={onPickDocument}
            disabled={uploading}
          />
          <Button
            title="Take photo"
            variant="secondary"
            onPress={() => onPickImage('camera')}
            disabled={uploading}
          />
          <Button
            title="Choose photo"
            variant="secondary"
            onPress={() => onPickImage('library')}
            disabled={uploading}
          />
        </View>

        {validationError ? (
          <View style={styles.banner}>
            <Text variant="small" style={styles.bannerText}>
              {validationError}
            </Text>
          </View>
        ) : null}

        {uploading ? (
          <View style={styles.progressBlock}>
            {phase === 'finalising' ? (
              // Confirm step reports no progress — spinner + clear label rather
              // than a bar pinned at 100%.
              <View style={styles.indeterminateRow}>
                <Spinner size="small" />
                <Text variant="small" muted>
                  Finalising…
                </Text>
              </View>
            ) : progressSeen ? (
              <>
                <ProgressBar progress={progress} />
                <Text variant="small" muted>
                  Uploading… {Math.round(progress * 100)}%
                </Text>
              </>
            ) : (
              // No byte-progress reported yet (or ever, on some Android
              // providers) — indeterminate spinner instead of a stuck bar.
              <View style={styles.indeterminateRow}>
                <Spinner size="small" />
                <Text variant="small" muted>
                  Uploading…
                </Text>
              </View>
            )}
          </View>
        ) : null}

        <FormError error={mutation.error} fallback="Upload failed. Please try again." />

        <View style={styles.actions}>
          <Button
            title="Upload"
            onPress={onUpload}
            loading={uploading}
            disabled={!selected || !!validationError || uploading}
          />
          <Button
            title="Cancel"
            variant="ghost"
            onPress={() => router.back()}
            disabled={uploading}
          />
        </View>
      </View>
    </ScreenContainer>
  );
}

/** Build a filename from an image URI when the picker doesn't supply one. */
function deriveImageName(uri: string, contentType: string): string {
  const fromUri = uri.split('/').pop();
  if (fromUri && fromUri.includes('.')) return fromUri;
  const ext = contentType === 'image/png' ? 'png' : contentType === 'image/webp' ? 'webp' : 'jpg';
  return `photo.${ext}`;
}

const styles = StyleSheet.create({
  body: {
    paddingTop: spacing.md,
    gap: spacing.md,
  },
  selectedBlock: {
    gap: spacing.xs,
  },
  pickers: {
    gap: spacing.sm,
  },
  progressBlock: {
    gap: spacing.sm,
  },
  indeterminateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  actions: {
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  banner: {
    backgroundColor: colors.errorSurface,
    borderWidth: 1,
    borderColor: colors.error,
    borderRadius: radii.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  bannerText: {
    color: colors.error,
  },
});
