import { zodResolver } from '@hookform/resolvers/zod';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Controller, useForm, type Control } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';

import { useCreateSupplierPayment } from '@/src/api/mutations/useCreateSupplierPayment';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageSupplierPayments } from '@/src/auth/permissions';
import {
  Button,
  DateField,
  FormError,
  Input,
  ScreenContainer,
  Select,
  Text,
  useToast,
} from '@/src/components/ui';
import {
  defaultSupplierPaymentFormValues,
  supplierPaymentSchema,
  toCreateBody,
  type SupplierPaymentFormValues,
} from '@/src/forms/supplierPaymentSchema';
import { newIdempotencyKey } from '@/src/lib/idempotency';
import { colors, spacing } from '@/src/theme/tokens';

const PAYMENT_TYPE_OPTIONS = [
  { value: 'full', label: 'Full' },
  { value: 'partial', label: 'Partial' },
  { value: 'deposit', label: 'Deposit' },
];

export default function RecordSupplierPaymentForm() {
  const { id, invoiceId } = useLocalSearchParams<{ id: string; invoiceId: string }>();
  const router = useRouter();
  const { showToast } = useToast();
  const { user } = useAuth();
  const mutation = useCreateSupplierPayment(invoiceId, id);

  // One key per form mount, reused for every submit of this session. A retry
  // after a lost response carries the same key → the server returns the cached
  // result instead of creating a second payment. A fresh open = a fresh key.
  const [idempotencyKey] = useState(() => newIdempotencyKey());

  const { control, handleSubmit, formState } = useForm<SupplierPaymentFormValues>({
    resolver: zodResolver(supplierPaymentSchema),
    defaultValues: defaultSupplierPaymentFormValues,
    mode: 'onTouched',
  });

  // Defense-in-depth: the button that opens this route is already admin-gated
  // and the server is `require_admin`, but a deep link could land a non-admin
  // here. Show a clear message rather than a form they can't submit.
  if (!canManageSupplierPayments(user?.role as UserRole | undefined)) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Record payment' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to record supplier payments.
        </Text>
        <Button title="Close" variant="ghost" onPress={() => router.back()} />
      </ScreenContainer>
    );
  }

  const onSubmit = handleSubmit((values) => {
    mutation.mutate(
      { body: toCreateBody(values), idempotencyKey },
      {
        onSuccess: () => {
          // Success toast lands on the detail screen after the modal closes;
          // an error keeps the modal open and renders inline via <FormError>
          // (a root toast is hidden behind the modal). See AGENTS.md → Toasts.
          showToast('Payment recorded', 'success');
          router.back();
        },
      },
    );
  });

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title: 'Record supplier payment' }} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
      >
        <ScrollView
          contentContainerStyle={styles.form}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
        >
        <TextField control={control} name="swift_ref" label="SWIFT reference" />

        <Controller
          control={control}
          name="payment_date"
          render={({ field, fieldState }) => (
            <DateField
              label="Payment date"
              value={field.value}
              onChange={field.onChange}
              error={fieldState.error?.message}
            />
          )}
        />

        <Controller
          control={control}
          name="amount"
          render={({ field, fieldState }) => (
            <Input
              label="Amount (USD)"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              keyboardType="decimal-pad"
              placeholder="0.00"
              error={fieldState.error?.message}
            />
          )}
        />

        {/* Currency is fixed to USD — shown as a static label, not editable. */}
        <View style={styles.staticField}>
          <Text variant="small" muted>
            Currency
          </Text>
          <Text variant="body">USD</Text>
        </View>

        <Controller
          control={control}
          name="payment_type"
          render={({ field, fieldState }) => (
            <View>
              <Select
                label="Payment type"
                value={field.value || null}
                options={PAYMENT_TYPE_OPTIONS}
                onChange={field.onChange}
                placeholder="Select a payment type"
              />
              {fieldState.error ? (
                <Text variant="small" style={styles.fieldError}>
                  {fieldState.error.message}
                </Text>
              ) : null}
            </View>
          )}
        />

        <TextField control={control} name="bank_name" label="Bank name (optional)" />
        <TextField control={control} name="notes" label="Notes (optional)" multiline />

        <FormError error={mutation.error} fallback="Could not record payment" />

        <View style={styles.actions}>
          <Button
            title="Record payment"
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

function TextField({
  control,
  name,
  label,
  multiline,
}: {
  control: Control<SupplierPaymentFormValues>;
  name: keyof SupplierPaymentFormValues;
  label: string;
  multiline?: boolean;
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Input
          label={label}
          value={field.value}
          onChangeText={field.onChange}
          onBlur={field.onBlur}
          multiline={multiline}
          style={multiline ? styles.multiline : undefined}
          error={fieldState.error?.message}
        />
      )}
    />
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
  multiline: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  staticField: {
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  fieldError: {
    color: colors.error,
    marginTop: -spacing.sm,
    marginBottom: spacing.md,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
