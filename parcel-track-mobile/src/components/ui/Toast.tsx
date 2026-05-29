/**
 * Global toast — the single feedback channel for mutation success/error.
 *
 * `ToastProvider` is mounted once at the root (see `app/_layout.tsx`). Any
 * screen calls `useToast().showToast(message, tone)`; the provider renders an
 * absolutely-positioned, auto-dismissing banner near the bottom of the screen.
 *
 * Hand-rolled (no dependency) — a fade in/out via `Animated`, ~3s visible.
 * Calling `showToast` again while one is visible replaces it and restarts the
 * timer, so rapid mutations don't stack banners.
 */

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, radii, spacing } from '../../theme/tokens';
import { Text } from './Text';

export type ToastTone = 'success' | 'error' | 'info';

interface ToastContextValue {
  showToast: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const VISIBLE_MS = 3000;
const FADE_MS = 200;

interface ToastState {
  message: string;
  tone: ToastTone;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const opacity = useRef(new Animated.Value(0)).current;
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insets = useSafeAreaInsets();

  const clearTimer = () => {
    if (hideTimer.current) {
      clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
  };

  const showToast = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      clearTimer();
      setToast({ message, tone });
      Animated.timing(opacity, {
        toValue: 1,
        duration: FADE_MS,
        useNativeDriver: true,
      }).start();
      hideTimer.current = setTimeout(() => {
        Animated.timing(opacity, {
          toValue: 0,
          duration: FADE_MS,
          useNativeDriver: true,
        }).start(() => setToast(null));
      }, VISIBLE_MS);
    },
    [opacity],
  );

  // Clear any pending timer if the provider unmounts.
  useEffect(() => clearTimer, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {toast ? (
        <Animated.View
          pointerEvents="none"
          style={[
            styles.container,
            { bottom: insets.bottom + spacing.lg, opacity, backgroundColor: toneColor[toast.tone] },
          ]}
        >
          <Text style={styles.message}>{toast.message}</Text>
        </Animated.View>
      ) : null}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used inside <ToastProvider>');
  }
  return ctx;
}

const toneColor: Record<ToastTone, string> = {
  success: colors.success,
  error: colors.error,
  info: colors.text,
};

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: spacing.lg,
    right: spacing.lg,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radii.md,
  },
  message: {
    color: colors.primaryText,
    textAlign: 'center',
  },
});
