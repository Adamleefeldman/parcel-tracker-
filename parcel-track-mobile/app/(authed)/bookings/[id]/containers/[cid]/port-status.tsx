import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useUpdatePortStatus } from '../../../../../../src/api/mutations/useUpdatePortStatus';
import { useContainer } from '../../../../../../src/api/queries/useContainer';
import type { PortStatus } from '../../../../../../src/api/types/enums';
import {
  Button,
  FormError,
  Input,
  ScreenContainer,
  Select,
  Spinner,
  Text,
  useToast,
} from '../../../../../../src/components/ui';
import { humanizeStatus } from '../../../../../../src/components/ui/statusPillMapping';
import { spacing } from '../../../../../../src/theme/tokens';

// Exhaustive label map — `Record<PortStatus, string>` fails the typecheck if
// the backend grows a new PortStatus value (mirror in `enums.ts`), so the
// Select options can never silently drift out of sync with the enum.
const PORT_STATUS_LABELS: Record<PortStatus, string> = {
  not_arrived: humanizeStatus('not_arrived'),
  awaiting_customs: humanizeStatus('awaiting_customs'),
  customs_hold: humanizeStatus('customs_hold'),
  released: humanizeStatus('released'),
};

const PORT_STATUS_OPTIONS = (Object.keys(PORT_STATUS_LABELS) as PortStatus[]).map((value) => ({
  value,
  label: PORT_STATUS_LABELS[value],
}));

export default function PortStatusForm() {
  const { id, cid } = useLocalSearchParams<{ id: string; cid: string }>();
  const router = useRouter();
  const { showToast } = useToast();
  const { data: container, isLoading } = useContainer(id, cid);
  const mutation = useUpdatePortStatus(id, cid);

  const [portStatus, setPortStatus] = useState<PortStatus | null>(null);
  const [destin8Ref, setDestin8Ref] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);

  // Pre-fill once the container loads. `null` local state means "not yet
  // touched" — fall back to the container's current value for display.
  const currentPortStatus = portStatus ?? container?.port_status ?? null;
  const currentDestin8 = destin8Ref ?? container?.destin8_ref ?? '';
  const currentNotes = notes ?? container?.notes ?? '';

  const onSubmit = () => {
    const trimmedRef = currentDestin8.trim();
    const trimmedNotes = currentNotes.trim();
    mutation.mutate(
      {
        port_status: currentPortStatus ?? undefined,
        destin8_ref: trimmedRef === '' ? undefined : trimmedRef,
        notes: trimmedNotes === '' ? undefined : trimmedNotes,
      },
      {
        onSuccess: () => {
          // Toast on success only — it shows on the detail screen once the
          // modal dismisses. In-modal errors render inline via <FormError>
          // (a root toast would be hidden behind the modal). See FormError.
          showToast('Status updated', 'success');
          router.back();
        },
      },
    );
  };

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title: 'Update port status' }} />
      {isLoading ? (
        <Spinner centered />
      ) : (
        <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
          <Select
            label="Port status"
            value={currentPortStatus}
            options={PORT_STATUS_OPTIONS}
            onChange={(v) => setPortStatus(v as PortStatus)}
            placeholder="Select a port status"
          />
          <Input
            label="Destin8 ref"
            value={currentDestin8}
            onChangeText={setDestin8Ref}
            placeholder="e.g. D8-12345"
            autoCapitalize="characters"
          />
          <Input
            label="Notes"
            value={currentNotes}
            onChangeText={setNotes}
            placeholder="Optional notes"
            multiline
            numberOfLines={4}
            style={styles.notes}
          />
          <FormError error={mutation.error} fallback="Could not update status" />
          <View style={styles.actions}>
            <Button
              title="Save changes"
              onPress={onSubmit}
              loading={mutation.isPending}
              disabled={mutation.isPending}
            />
            <Button title="Cancel" variant="ghost" onPress={() => router.back()} />
          </View>
          <Text variant="small" muted style={styles.hint}>
            Visible to all booking members.
          </Text>
        </ScrollView>
      )}
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  form: {
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
  },
  notes: {
    minHeight: 96,
    textAlignVertical: 'top',
  },
  actions: {
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  hint: {
    marginTop: spacing.md,
    textAlign: 'center',
  },
});
