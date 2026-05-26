/**
 * Tiny pub/sub for "session is unrecoverably dead" signals.
 *
 * `apiRequest` lives in a pure module and can't reach React state. When a
 * refresh attempt fails (so we've already cleared tokens), it emits here and
 * AuthProvider — subscribed in a useEffect — flips status to `anonymous`,
 * which renders LoginScreen.
 *
 * No payload: the only fact being communicated is "stop trusting the stored
 * tokens." Callers must call `clearTokens()` before emitting; this module
 * does not touch storage.
 */

type Listener = () => void;

const listeners = new Set<Listener>();

export function onSessionExpired(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function emitSessionExpired(): void {
  for (const listener of listeners) {
    listener();
  }
}
