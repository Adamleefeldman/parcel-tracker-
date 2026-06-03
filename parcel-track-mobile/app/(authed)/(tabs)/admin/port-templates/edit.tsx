import { zodResolver } from '@hookform/resolvers/zod';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import React from 'react';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';

import { useUpsertPortTemplate } from '@/src/api/mutations/useUpsertPortTemplate';
import { usePortTemplates } from '@/src/api/queries/usePortTemplates';
import type { PortTemplate } from '@/src/api/types/admin';
import { UK_PORT_LABELS, type UKPort, type UserRole } from '@/src/api/types/enums';
import { useAuth } from '@/src/auth/AuthContext';
import { canManageAdmin } from '@/src/auth/permissions';
import {
  Button,
  ErrorState,
  FormError,
  Input,
  ScreenContainer,
  Spinner,
  Text,
  useToast,
} from '@/src/components/ui';
import {
  defaultPortTemplateFormValues,
  portTemplateSchema,
  toUpsertBody,
  type PortTemplateFormValues,
} from '@/src/forms/portTemplateSchema';
import { spacing } from '@/src/theme/tokens';

const VALID_PORTS = Object.keys(UK_PORT_LABELS) as UKPort[];

/**
 * Edit (upsert) a port template. The target port arrives as the `port` **query
 * param** (a static modal route — not a dynamic `[port]` segment, which doesn't
 * reliably bind to useLocalSearchParams for an explicitly-registered modal).
 * Pre-fills from the existing template (warm from the list query cache; cold
 * load fetches it), or defaults for a port with no saved row. PUTs to upsert —
 * there is no separate create. Money discipline: rate fields stay strings;
 * free-days are ints (see `portTemplateSchema`).
 */
export default function EditPortTemplateScreen() {
  const { port } = useLocalSearchParams<{ port: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = canManageAdmin(user?.role as UserRole | undefined);
  const { data, isLoading, isError, error, refetch } = usePortTemplates({ enabled: isAdmin });

  const validPort = VALID_PORTS.includes(port as UKPort) ? (port as UKPort) : null;
  const title = validPort ? UK_PORT_LABELS[validPort] : 'Port template';

  if (!isAdmin) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title }} />
        <Text variant="body" muted style={styles.notPermitted}>
          You don&apos;t have permission to manage port templates.
        </Text>
        <Button title="Close" variant="ghost" onPress={() => router.back()} />
      </ScreenContainer>
    );
  }

  if (!validPort) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title }} />
        <Text variant="body" muted style={styles.notPermitted}>
          Unknown port.
        </Text>
        <Button title="Close" variant="ghost" onPress={() => router.back()} />
      </ScreenContainer>
    );
  }

  if (isLoading) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title }} />
        <Spinner centered />
      </ScreenContainer>
    );
  }

  if (isError) {
    return (
      <ScreenContainer>
        <Stack.Screen options={{ title }} />
        <ErrorState error={error} onRetry={() => refetch()} />
      </ScreenContainer>
    );
  }

  const existing = (data ?? []).find((t) => t.port === validPort);
  return <PortTemplateForm port={validPort} existing={existing} title={title} />;
}

function PortTemplateForm({
  port,
  existing,
  title,
}: {
  port: UKPort;
  existing: PortTemplate | undefined;
  title: string;
}) {
  const router = useRouter();
  const { showToast } = useToast();
  const mutation = useUpsertPortTemplate();

  const defaults: PortTemplateFormValues = existing
    ? {
        free_days_detention: String(existing.free_days_detention),
        free_days_demurrage: String(existing.free_days_demurrage),
        detention_rate_gbp_after: existing.detention_rate_gbp_after ?? '',
        demurrage_rate_gbp_after: existing.demurrage_rate_gbp_after ?? '',
      }
    : defaultPortTemplateFormValues;

  const { control, handleSubmit, formState } = useForm<PortTemplateFormValues>({
    resolver: zodResolver(portTemplateSchema),
    defaultValues: defaults,
    mode: 'onTouched',
  });

  const onSubmit = handleSubmit((values) => {
    mutation.mutate(
      { port, body: toUpsertBody(values) },
      {
        onSuccess: () => {
          showToast('Port template saved', 'success');
          router.back();
        },
      },
    );
  });

  return (
    <ScreenContainer>
      <Stack.Screen options={{ title }} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
      >
        <ScrollView
          contentContainerStyle={styles.form}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
        >
          <Text variant="small" muted style={styles.intro}>
            Free-day defaults and post-free-time rates for {UK_PORT_LABELS[port]}. Leave a rate
            blank to leave it unset.
          </Text>

          <Controller
            control={control}
            name="free_days_detention"
            render={({ field, fieldState }) => (
              <Input
                label="Detention free days"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                keyboardType="number-pad"
                placeholder="0"
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="detention_rate_gbp_after"
            render={({ field, fieldState }) => (
              <Input
                label="Detention rate after free days (£/day, optional)"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                keyboardType="decimal-pad"
                placeholder="0.00"
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="free_days_demurrage"
            render={({ field, fieldState }) => (
              <Input
                label="Demurrage free days"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                keyboardType="number-pad"
                placeholder="0"
                error={fieldState.error?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="demurrage_rate_gbp_after"
            render={({ field, fieldState }) => (
              <Input
                label="Demurrage rate after free days (£/day, optional)"
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                keyboardType="decimal-pad"
                placeholder="0.00"
                error={fieldState.error?.message}
              />
            )}
          />

          <FormError error={mutation.error} fallback="Could not save port template" />

          <View style={styles.actions}>
            <Button
              title="Save template"
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
  intro: {
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
