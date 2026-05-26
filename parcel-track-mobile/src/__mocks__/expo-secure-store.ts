/**
 * In-memory stand-in for expo-secure-store under jest.
 *
 * Real SecureStore needs the Expo native runtime — it can't load under
 * plain node. This mock satisfies the same shape so tokenStorage.ts works
 * unchanged in tests.
 */

const store = new Map<string, string>();

export async function getItemAsync(key: string): Promise<string | null> {
  return store.has(key) ? (store.get(key) as string) : null;
}

export async function setItemAsync(key: string, value: string): Promise<void> {
  store.set(key, value);
}

export async function deleteItemAsync(key: string): Promise<void> {
  store.delete(key);
}

export function __reset(): void {
  store.clear();
}
