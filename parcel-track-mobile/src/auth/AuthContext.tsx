/**
 * Auth state provider.
 *
 * Owns the source of truth for "is the user signed in" and exposes:
 *   - status: 'loading' | 'anonymous' | 'authenticated'
 *   - signIn(email, password)
 *   - signOut()
 *
 * On mount, checks SecureStore for an existing access token to skip the
 * login screen on warm starts. We do NOT validate the token with the server
 * here — that happens lazily on the first authenticated request (401 →
 * future refresh-token flow). Keeps cold start cheap.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

import { loginRequest } from './authApi';
import { clearTokens, getAccessToken, setTokens } from './tokenStorage';

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated';

interface AuthContextValue {
  status: AuthStatus;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');

  // Cold-start: check SecureStore for an existing token.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = await getAccessToken();
      if (cancelled) return;
      setStatus(token ? 'authenticated' : 'anonymous');
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const tokens = await loginRequest(email, password);
    await setTokens(tokens);
    setStatus('authenticated');
  }, []);

  const signOut = useCallback(async () => {
    await clearTokens();
    setStatus('anonymous');
  }, []);

  return (
    <AuthContext.Provider value={{ status, signIn, signOut }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
