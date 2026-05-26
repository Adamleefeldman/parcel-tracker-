/**
 * Token storage for JWT access + refresh tokens.
 *
 * Backed by expo-secure-store (Keychain on iOS, EncryptedSharedPreferences on Android).
 * NEVER store credentials in AsyncStorage — it's plaintext on disk.
 *
 * All call sites should go through this module so we have one place to:
 *   - rotate key naming
 *   - add encryption-at-rest options
 *   - wire token-refresh logic
 *   - clear everything on logout
 */

import * as SecureStore from 'expo-secure-store';

// SecureStore key rules: alphanumerics, ".", "-", "_" only.
const ACCESS_TOKEN_KEY = 'fmcghub.auth.accessToken';
const REFRESH_TOKEN_KEY = 'fmcghub.auth.refreshToken';

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

export async function setTokens({ accessToken, refreshToken }: TokenPair): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken),
    SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken),
  ]);
}

export async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}
