/**
 * In-memory stand-in for expo-crypto under jest.
 *
 * Real expo-crypto needs the Expo native runtime — it can't load under plain
 * node. This mock satisfies the `randomUUID()` shape `src/lib/idempotency.ts`
 * uses, returning a fresh RFC4122-v4-shaped string each call (good enough for
 * uniqueness assertions; not cryptographically random — it's a test double).
 */

let counter = 0;

export function randomUUID(): string {
  counter += 1;
  const seg = (n: number, len: number) => n.toString(16).padStart(len, '0').slice(-len);
  const rand = Math.floor(Math.random() * 0xffffffff);
  return `${seg(counter, 8)}-${seg(rand, 4)}-4${seg(rand, 3)}-8${seg(counter, 3)}-${seg(rand, 12)}`;
}

export function __reset(): void {
  counter = 0;
}
