import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';

import { useOpenDispute } from '@/src/api/mutations/useOpenDispute';
import {
  Button,
  FormError,
  Input,
  ScreenContainer,
  Text,
  useToast,
} from '@/src/components/ui';
import { spacing } from '@/src/theme/tokens';

export default function DisputeForm() {
  const { id, cid } = useLocalSearchParams<{ id: string; cid: string }>();
  const router = useRouter();
  const { showToast } = useToast();
  const mutation = useOpenDispute(id, cid);

  const [reason, setReason] = useState('');
  const trimmed = reason.trim();
  const canSubmit = trimmed.length > 0 && !mutation.isPending;

  const onSubmit = () => {
    mutation.mutate(
      { reason: trimmed },
      {
        onSuccess: () => {
          // Success toast shows on the detail screen after the modal closes;
          // errors render inline via <FormError> (a root toast is hidden
          // behind the open modal). See FormError.
          showToast('Dispute opened', 'success');
          router.back();
        },
      },
    );
  };

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title: 'Open dispute' }} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
      >
        <ScrollView
          contentContainerStyle={styles.form}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
        >
        <Text variant="body" muted style={styles.intro}>
          Opening a dispute marks this container as disputed and blocks the booking from
          completing until an admin acknowledges it.
        </Text>
        <Input
          label="Reason"
          value={reason}
          onChangeText={setReason}
          placeholder="Describe the issue"
          multiline
          numberOfLines={4}
          style={styles.reason}
          autoFocus
        />
        <FormError error={mutation.error} fallback="Could not open dispute" />
        <View style={styles.actions}>
          <Button
            title="Open dispute"
            onPress={onSubmit}
            loading={mutation.isPending}
            disabled={!canSubmit}
          />
          <Button title="Cancel" variant="ghost" onPress={() => router.back()} />
        </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  form: {
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
  },
  intro: {
    marginBottom: spacing.md,
  },
  reason: {
    minHeight: 96,
    textAlignVertical: 'top',
  },
  actions: {
    gap: spacing.sm,
    marginTop: spacing.md,
  },
});
