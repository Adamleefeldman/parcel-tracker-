import { zodResolver } from '@hookform/resolvers/zod';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Controller, useForm, type Control } from 'react-hook-form';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useCreateCustomerPayment } from '@/src/api/mutations/useCreateCustomerPayment';
import type { UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageCustomerPayments } from '@/src/auth/permissions';
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
  customerPaymentSchema,
  defaultPaymentFormValues,
  toCreateBody,
  type CustomerPaymentFormValues,
} from '@/src/forms/customerPaymentSchema';
import { newIdempotencyKey } from '@/src/lib/idempotency';
import { colors, spacing } from '@/src/theme/tokens';

const METHOD_OPTIONS = [
  { value: 'transfer', label: 'Bank transfer' },
  { value: 'cash', label: 'Cash' },
];

export default function RecordPaymentForm() {
  const { id, cid } = useLocalSearchParams<{ id: string; cid: string }>();
  const router = useRouter();
  const { showToast } = useToast();
  const { user } = useAuth();
  const mutation = useCreateCustomerPayment(id, cid);

  // One key per form mount, reused for every submit of this session. A retry
  // after a lost response carries the same key → the server returns the cached
  // result instead of creating a second tranche. A fresh open = a fresh key.
  const [idempotencyKey] = useState(() => newIdempotencyKey());

  const { control, handleSubmit, watch, formState } = useForm<CustomerPaymentFormValues>({
    resolver: zodResolver(customerPaymentSchema),
    defaultValues: defaultPaymentFormValues,
    mode: 'onTouched',
  });

  const isTransfer = watch('method') === 'transfer';

  // Defense-in-depth: the button that opens this route is already admin-gated
  // and the server is `require_admin`, but a deep link could land a non-admin
  // here. Show a clear message rather than a form they can't submit.
  if (!canManageCustomerPayments(user?.role as UserRole | undefined)) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title: 'Record payment' }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don't have permission to record payments.
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
      <Stack.Screen options={{ title: 'Record payment' }} />
      <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
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
          name="method"
          render={({ field, fieldState }) => (
            <View>
              <Select
                label="Method"
                value={field.value || null}
                options={METHOD_OPTIONS}
                onChange={field.onChange}
                placeholder="Select a payment method"
              />
              {fieldState.error ? (
                <Text variant="small" style={styles.fieldError}>
                  {fieldState.error.message}
                </Text>
              ) : null}
            </View>
          )}
        />

        <MoneyInput control={control} name="amount_received" label="Amount received (£)" />
        <MoneyInput control={control} name="banked_total" label="Banked total (£)" />
        <MoneyInput control={control} name="variance" label="Variance (£, +/−)" />
        <MoneyInput control={control} name="expense_courier" label="Courier expense (£)" />
        <MoneyInput control={control} name="expense_bank_charge" label="Bank charge (£)" />

        {isTransfer ? (
          <>
            <TextField control={control} name="sender_bank" label="Sender bank" />
            <TextField control={control} name="receiver_bank" label="Receiver bank" />
          </>
        ) : null}

        <TextField
          control={control}
          name="tranche_index"
          label="Tranche #"
          keyboardType="number-pad"
        />
        <TextField control={control} name="customer_invoice_ref" label="Invoice reference" />
        <TextField control={control} name="notes" label="Notes" multiline />

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
    </ScreenContainer>
  );
}

/** Decimal-pad money input. Value stays a string — never coerced to a number. */
function MoneyInput({
  control,
  name,
  label,
}: {
  control: Control<CustomerPaymentFormValues>;
  name: keyof CustomerPaymentFormValues;
  label: string;
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
          keyboardType="decimal-pad"
          placeholder="0.00"
          error={fieldState.error?.message}
        />
      )}
    />
  );
}

function TextField({
  control,
  name,
  label,
  keyboardType,
  multiline,
}: {
  control: Control<CustomerPaymentFormValues>;
  name: keyof CustomerPaymentFormValues;
  label: string;
  keyboardType?: 'number-pad';
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
          keyboardType={keyboardType}
          multiline={multiline}
          style={multiline ? styles.multiline : undefined}
          error={fieldState.error?.message}
        />
      )}
    />
  );
}

const styles = StyleSheet.create({
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
  fieldError: {
    color: colors.error,
    marginTop: -spacing.sm,
    marginBottom: spacing.md,
  },
  notPermitted: {
    marginVertical: spacing.lg,
  },
});
