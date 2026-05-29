/**
 * Idempotency-Key generation for safe-to-retry financial POSTs.
 *
 * The backend's financial create endpoints (customer payments, and future
 * supplier payments) REQUIRE an `Idempotency-Key` header — missing it is a
 * 400. The server caches the response 24h, so a repeat with the same key
 * returns the original result without re-processing. That makes a lost-
 * response retry safe: a dropped network reply followed by a resubmit can't
 * create two payments.
 *
 * Lifecycle: generate ONE key per form mount and reuse it for every submit of
 * that form session (see the record-payment form). A fresh form open = a
 * fresh key.
 *
 * `expo-crypto`'s `randomUUID()` is a synchronous RFC4122 v4 UUID — no browser
 * `crypto.randomUUID()` (that global doesn't exist in Hermes).
 */

import * as Crypto from 'expo-crypto';

export const newIdempotencyKey = (): string => Crypto.randomUUID();
