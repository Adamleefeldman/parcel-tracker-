import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, View } from 'react-native';

import { ApiError } from '../../src/api/client';
import { useAuth } from '../../src/auth/AuthContext';
import { Button, Input, ScreenContainer, Text } from '../../src/components/ui';
import { colors, spacing } from '../../src/theme/tokens';

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const onSubmit = async () => {
    if (!email.trim() || !password) {
      setErrorMsg('Email and password are required.');
      return;
    }
    setErrorMsg(null);
    setSubmitting(true);
    try {
      // Backend stores lowercase email; phone keyboards can auto-capitalize despite autoCapitalize="none".
      await signIn(email.trim().toLowerCase(), password);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Login failed. Please try again.';
      setErrorMsg(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScreenContainer>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.container}
      >
        <View style={styles.inner}>
          <Text variant="display" style={styles.title}>
            FMCG Hub
          </Text>
          <Text variant="body" muted style={styles.subtitle}>
            Sign in to continue
          </Text>

          <Input
            placeholder="Email"
            autoCapitalize="none"
            autoComplete="email"
            textContentType="emailAddress"
            autoCorrect={false}
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
            editable={!submitting}
          />

          <Input
            placeholder="Password"
            autoCapitalize="none"
            autoComplete="current-password"
            textContentType="password"
            autoCorrect={false}
            secureTextEntry
            value={password}
            onChangeText={setPassword}
            editable={!submitting}
            onSubmitEditing={onSubmit}
          />

          {errorMsg ? (
            <Text variant="small" style={styles.error}>
              {errorMsg}
            </Text>
          ) : null}

          <Button title="Sign in" loading={submitting} onPress={onSubmit} />
        </View>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  inner: {
    flex: 1,
    justifyContent: 'center',
  },
  title: {
    marginBottom: spacing.xs,
    textAlign: 'center',
  },
  subtitle: {
    marginBottom: spacing.xxl,
    textAlign: 'center',
  },
  error: {
    color: colors.error,
    marginBottom: spacing.md,
    textAlign: 'center',
  },
});
