/**
 * Auth state provider.
 *
 * Owns the source of truth for "is the user signed in" and exposes:
 *   - status: 'loading' | 'anonymous' | 'authenticated'
 *   - user:   decoded from the access token (id + role); null when anonymous
 *   - signIn(email, password)
 *   - signOut()
 *
 * Cold start: trust whatever access token sits in SecureStore. We do NOT
 * ping the server to validate — the first real authenticated request will
 * self-heal via the 401-refresh flow in apiRequest. Cheap boot.
 *
 * Session death: when apiRequest's refresh attempt fails (refresh token
 * dead, server says no), it clears tokens and emits a session-expired
 * event; we listen here and flip status → 'anonymous'.
 *
 * User cache: derived from the JWT payload, not a /me fetch. When the
 * backend grows a /me endpoint, swap decodeUserFromToken for a real call
 * and extend the User type to include name + email.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

import { loginRequest } from './authApi';
import { decodeUserFromToken, type User } from './jwt';
import { onSessionExpired } from './sessionEvents';
import { clearTokens, getAccessToken, setTokens } from './tokenStorage';

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated';

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<User | null>(null);

  // Cold-start: check SecureStore for an existing token and derive the user.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = await getAccessToken();
      if (cancelled) return;
      if (token) {
        setUser(decodeUserFromToken(token));
        setStatus('authenticated');
      } else {
        setStatus('anonymous');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Subscribe to session-expired events emitted by apiRequest on
  // unrecoverable refresh failures. Tokens are already cleared by then;
  // we just flip UI state.
  useEffect(() => {
    return onSessionExpired(() => {
      setUser(null);
      setStatus('anonymous');
    });
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const tokens = await loginRequest(email, password);
    await setTokens(tokens);
    setUser(decodeUserFromToken(tokens.accessToken));
    setStatus('authenticated');
  }, []);

  const signOut = useCallback(async () => {
    await clearTokens();
    setUser(null);
    setStatus('anonymous');
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
