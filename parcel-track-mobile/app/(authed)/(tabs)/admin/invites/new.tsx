import { zodResolver } from '@hookform/resolvers/zod';
import { Stack, useRouter } from 'expo-router';
import React from 'react';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';

import { useSendInvite } from '@/src/api/mutations/useSendInvite';
import { USER_ROLES, USER_ROLE_LABELS, type UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import {
  Button,
  FormError,
  Input,
  ScreenContainer,
  Select,
  Text,
  useToast,
} from '@/src/components/ui';
import {
  defaultInviteFormValues,
  inviteSchema,
  toCreateBody,
  type InviteFormValues,
} from '@/src/forms/inviteSchema';
import { colors, spacing } from '@/src/theme/tokens';

const ROLE_OPTIONS = USER_ROLES.map((role) => ({ value: role, label: USER_ROLE_LABELS[role] }));

/**
 * Send-invite modal form (Admin → People → Invites). Reuses `POST /auth/invite`
 * via `useSendInvite`. No Idempotency-Key (not a financial create). Success →
 * toast + `router.back()` (the toast lands on the invites list behind the
 * modal); errors render inline via `<FormError>` (toasts don't paint over
 * modals — see AGENTS.md → Toasts).
 */
export default function NewInviteScreen() {
  const router = useRouter();
  const { showToast } = useToast();
  const { user } = useAuth();
  const mutation = useSendInvite();

  const { control, handleSubmit, formState } = useForm<InviteFormValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: defaultInviteFormValues,
    mode: 'onTouched',
  });

  if (!canManageAdmin(user?.role as UserRole | undefined)) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Send invite' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to send invites.
        </Text>
        <Button title="Close" variant="ghost" onPress={() => router.back()} />
      </ScreenContainer>
    );
  }

  const onSubmit = handleSubmit((values) => {
    mutation.mutate(toCreateBody(values), {
      onSuccess: () => {
        showToast('Invite sent', 'success');
        router.back();
      },
    });
  });

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title: 'Send invite' }} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
      >
        <ScrollView
          contentContainerStyle={styles.form}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
        >
          <Controller
            control={control}
            name="email"
            render={({ field, fieldState }) => (
              <Input
                label="Email"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                placeholder="person@example.com"
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="role"
            render={({ field, fieldState }) => (
              <View>
                <Select
                  label="Role"
                  value={field.value || null}
                  options={ROLE_OPTIONS}
                  onChange={field.onChange}
                  placeholder="Select a role"
                />
                {fieldState.error ? (
                  <Text variant="small" style={styles.fieldError}>
                    {fieldState.error.message}
                  </Text>
                ) : null}
              </View>
            )}
          />

          <FormError error={mutation.error} fallback="Could not send invite" />

          <View style={styles.actions}>
            <Button
              title="Send invite"
              onPress={onSubmit}
              loading={mutation.isPending}
              disabled={mutation.isPending || !formState.isValid}
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
  fieldError: {
    color: colors.error,
    marginTop: -spacing.sm,
    marginBottom: spacing.md,
  },
  actions: {
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
