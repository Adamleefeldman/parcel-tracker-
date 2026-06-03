import { zodResolver } from '@hookform/resolvers/zod';
import { Stack, useRouter } from 'expo-router';
import React from 'react';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';

import { useCreateCompany } from '@/src/api/mutations/useCreateCompany';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import { Button, FormError, Input, ScreenContainer, Text, useToast } from '@/src/components/ui';
import {
  companySchema,
  defaultCompanyFormValues,
  toCreateBody,
  type CompanyFormValues,
} from '@/src/forms/companySchema';
import { spacing } from '@/src/theme/tokens';

/**
 * Create-end-customer modal form. No Idempotency-Key (not a financial create).
 * `aliases` is a single comma-separated text field; `toCreateBody` splits it
 * into the backend's `string[]`.
 */
export default function NewEndCustomerScreen() {
  const router = useRouter();
  const { showToast } = useToast();
  const { user } = useAuth();
  const mutation = useCreateCompany();

  const { control, handleSubmit, formState } = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: defaultCompanyFormValues,
    mode: 'onTouched',
  });

  if (!canManageAdmin(user?.role as UserRole | undefined)) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Add customer' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to add end customers.
        </Text>
        <Button title="Close" variant="ghost" onPress={() => router.back()} />
      </ScreenContainer>
    );
  }

  const onSubmit = handleSubmit((values) => {
    mutation.mutate(toCreateBody(values), {
      onSuccess: () => {
        showToast('End customer added', 'success');
        router.back();
      },
    });
  });

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title: 'Add customer' }} />
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
            name="legal_name"
            render={({ field, fieldState }) => (
              <Input
                label="Legal name"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                placeholder="Registered company name"
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="aliases"
            render={({ field, fieldState }) => (
              <Input
                label="Aliases (optional, comma-separated)"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                placeholder="Acme, Acme UK, Acme Foods"
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="registration_no"
            render={({ field, fieldState }) => (
              <Input
                label="Registration no. (optional)"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="vat_no"
            render={({ field, fieldState }) => (
              <Input
                label="VAT no. (optional)"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="default_address"
            render={({ field, fieldState }) => (
              <Input
                label="Default address (optional)"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                multiline
                style={styles.multiline}
                error={fieldState.error?.message}
              />
            )}
          />

          <FormError error={mutation.error} fallback="Could not add end customer" />

          <View style={styles.actions}>
            <Button
              title="Add customer"
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
  multiline: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  actions: {
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
