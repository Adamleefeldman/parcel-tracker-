import { zodResolver } from '@hookform/resolvers/zod';
import { Stack, useRouter } from 'expo-router';
import React from 'react';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';

import { useCreateBroker } from '@/src/api/mutations/useCreateBroker';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import { Button, FormError, Input, ScreenContainer, Text, useToast } from '@/src/components/ui';
import {
  brokerSchema,
  defaultBrokerFormValues,
  toCreateBody,
  type BrokerFormValues,
} from '@/src/forms/brokerSchema';
import { spacing } from '@/src/theme/tokens';

/** Create-broker modal form. No Idempotency-Key (not a financial create). */
export default function NewBrokerScreen() {
  const router = useRouter();
  const { showToast } = useToast();
  const { user } = useAuth();
  const mutation = useCreateBroker();

  const { control, handleSubmit, formState } = useForm<BrokerFormValues>({
    resolver: zodResolver(brokerSchema),
    defaultValues: defaultBrokerFormValues,
    mode: 'onTouched',
  });

  if (!canManageAdmin(user?.role as UserRole | undefined)) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Add broker' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to add brokers.
        </Text>
        <Button title="Close" variant="ghost" onPress={() => router.back()} />
      </ScreenContainer>
    );
  }

  const onSubmit = handleSubmit((values) => {
    mutation.mutate(toCreateBody(values), {
      onSuccess: () => {
        showToast('Broker added', 'success');
        router.back();
      },
    });
  });

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title: 'Add broker' }} />
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
            name="code"
            render={({ field, fieldState }) => (
              <Input
                label="Code"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                autoCapitalize="characters"
                placeholder="e.g. BRK-UK-01"
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="name"
            render={({ field, fieldState }) => (
              <Input
                label="Name"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                placeholder="Broker name"
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="phone"
            render={({ field, fieldState }) => (
              <Input
                label="Phone (optional)"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                keyboardType="phone-pad"
                placeholder="+44 …"
                error={fieldState.error?.message}
              />
            )}
          />

          <FormError error={mutation.error} fallback="Could not add broker" />

          <View style={styles.actions}>
            <Button
              title="Add broker"
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
  actions: {
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
