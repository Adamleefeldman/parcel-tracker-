---
name: idempotency-key
description: Use when designing or auditing POST endpoints that are unsafe to retry blindly — payments, supplier/customer invoices, refund creation, ticket/booking creation that produces a unique side effect, "send a message", "charge this card", or any mutation where a duplicate from a network retry would produce two of something instead of one. Triggers on phrases like "idempotency", "idempotency key", "safe to retry", "duplicate request", "network retried my POST and now I have two charges", "exactly-once API", "Idempotency-Key header", or when you see a payment / financial / message-creation endpoint with no header check. Also triggers on the inverse — code that uses an Idempotency-Key on a GET or on a non-mutating endpoint, which is a misuse.
---

# `Idempotency-Key` for unsafe-to-retry POSTs

Network retries are routine: mobile clients drop and reconnect, proxies retry idempotent verbs but sometimes get the classification wrong, load balancers re-dispatch on timeout. A blind retry of `POST /payments` creates two payments. The `Idempotency-Key` pattern lets clients safely retry: first request executes the mutation and caches the response; subsequent requests with the same key return the cached response without re-executing.

This is Stripe's pattern (their docs are excellent — read them if you're unfamiliar). What follows is the smallest correct implementation for FastAPI + Redis.

## When to apply this

Apply to endpoints where:

1. The request is a mutation (POST, occasionally PUT or PATCH that *creates* something — most PATCHes are inherently idempotent because they re-converge on the same end state).
2. A duplicate would be a real problem — a duplicate payment, a duplicate outbound email, a duplicate booking, a duplicate webhook fan-out.
3. The response can be meaningfully replayed — "here is the resource you just created, id=…".

Do **not** apply to:

- GETs and other safe verbs.
- PATCHes that are already idempotent by construction (`set status = X` produces the same end state regardless of how many times it runs).
- DELETEs that target a unique resource (the second delete returns 404 or a no-op).
- Bulk endpoints where the request body is itself the natural deduplication key (a `(user, hash_of_payload)` lookup serves you better than a client-generated UUID).

The mistake to avoid: requiring `Idempotency-Key` everywhere. It introduces friction (clients must generate UUIDs), and on read endpoints it serves no purpose. Apply it where retries cause real damage.

## The shape

Three pieces:

1. **A FastAPI dependency** that pulls the `Idempotency-Key` header, looks it up in Redis, and returns an `IdempotencyResult` with either a `cached_response` (handler returns it immediately) or a `store(response_body)` callback (handler runs normally and persists the response).
2. **A Redis-backed store** with a TTL (24h is a sensible default; long enough that a phone with a flaky connection can retry tomorrow, short enough that the key namespace doesn't grow forever).
3. **A dependency-shape API, not a decorator.** The handler stays in control of *what* gets cached — usually the serialized response, not the raw return value. A decorator that auto-caches is too magical and gets the cache key wrong on edge cases (e.g. when the handler raises 4xx).

## Canonical template

```python
# app/middleware/idempotency.py

from dataclasses import dataclass, field
from fastapi import Header, HTTPException, Request, status
from app.core.redis import get_redis

_IDEMPOTENCY_TTL = 86400  # 24 hours
_KEY_PREFIX = "idempotency:"


@dataclass
class IdempotencyResult:
    key: str
    cached_response: dict | list | None = None
    _request: Request | None = field(repr=False, default=None)

    async def store(self, response_body) -> None:
        """Persist the response so subsequent duplicate requests return it."""
        redis = get_redis_client()
        try:
            await redis.setex(
                f"{_KEY_PREFIX}{self.key}",
                _IDEMPOTENCY_TTL,
                json.dumps(response_body, default=str),
            )
        except Exception:
            # Redis is degraded — log and continue. The mutation already
            # committed; a missed cache write only means the *next* retry
            # re-executes. That's a non-event compared to a request failing.
            logger.warning("idempotency store failed", exc_info=True)


async def require_idempotency(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IdempotencyResult:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required for this endpoint.",
        )

    redis = await get_redis()
    try:
        cached = await redis.get(f"{_KEY_PREFIX}{idempotency_key}")
    except Exception:
        # Redis down — degrade open. Better to process the request and risk
        # a duplicate on retry than to refuse all writes when Redis is sick.
        logger.warning("idempotency check failed — degrading open", exc_info=True)
        cached = None

    if cached:
        try:
            return IdempotencyResult(
                key=idempotency_key,
                cached_response=json.loads(cached),
            )
        except json.JSONDecodeError:
            pass  # corrupted cache — re-process

    return IdempotencyResult(key=idempotency_key, _request=request)
```

### Handler usage

```python
@router.post("/invoices/{invoice_id}/supplier-payments", response_model=PaymentOut)
async def add_supplier_payment(
    invoice_id: UUID,
    body: PaymentCreate,
    idempotency: IdempotencyResult = Depends(require_idempotency),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    if idempotency.cached_response is not None:
        return idempotency.cached_response

    payment = await SupplierPaymentService.create(db, invoice_id, body, actor)
    await db.commit()

    # Serialize via the response_model schema so the cached payload matches
    # what the next retry will receive byte-for-byte.
    response_body = PaymentOut.model_validate(payment).model_dump(mode="json")
    await idempotency.store(response_body)
    return response_body
```

## Design rules — and why they matter

### Rule 1: Dependency, not decorator

A decorator that auto-wraps the handler tries to cache the *return value* and replay it. That fails when the handler raises an HTTPException (was that a cacheable rejection?), when the handler streams a response, when the handler needs to know whether it's running fresh or replaying. The dependency-shape API gives the handler the information and lets it decide.

### Rule 2: Cache the *serialized* response, not the ORM object

Cache what the client will see. Serializing through your Pydantic `response_model` is the right move — it guarantees the next retry gets a byte-for-byte equivalent payload, no matter what mutations happen to the ORM row later.

### Rule 3: Store *after* the mutation commits

`await idempotency.store(...)` only after `await db.commit()`. If you store before commit and the commit then fails, a retry sees the cached "success" response while the underlying row never existed.

### Rule 4: Don't try to make idempotency "exactly once"

`Idempotency-Key` gives you "at most once *visible* effect from the client's perspective", which is enough. There is a window where two simultaneous requests with the same key both miss the cache, both execute, and both write. Handling that requires a row-level lock on (idempotency_key) or a DB-side unique constraint that returns the existing row. In practice, almost all retries are serial (the client waits, times out, retries) — the parallel case is rare enough that letting one of the two writes win via a unique constraint elsewhere is the right complexity-to-benefit ratio.

### Rule 5: TTL of 24 hours is the right default

Long enough for a phone on a plane to retry tomorrow; short enough that the Redis key namespace doesn't grow without bound. Don't go to 7 days — the longer the TTL, the more likely you replay a stale response after underlying state has changed.

### Rule 6: Degrade open on Redis failure

If Redis is down when you check, log and process the request anyway. The alternative — refusing all idempotent writes — turns a Redis incident into an application incident. The cost of degrade-open is: a real retry during a Redis outage may produce a duplicate. The cost of degrade-closed is: every payment endpoint goes down whenever Redis hiccups. Pick the first one.

### Rule 7: 400, not 422, when the header is missing

`Idempotency-Key` is a request precondition, not a body validation failure. `400 Bad Request` with a message that names the header is the right shape.

### Rule 8: Don't validate that the key is a UUID

Clients use any string they want. Stripe accepts up to 255 characters of arbitrary text. The point is uniqueness *per logical request from one client*, not a particular shape. Validate length (e.g., < 256 chars) and that's it.

### Rule 9: One namespace per app

`idempotency:<key>`. Don't namespace by endpoint or by user — a key collision between users is astronomically unlikely if clients use UUIDs, and per-endpoint namespacing means a retry that hits a slightly different route (e.g., trailing slash) misses the cache.

### Rule 10: The cached response replays the status code too, when needed

If the original response was a 201 with a Location header, callers may want both. The minimal version (cache the JSON body) is usually enough; if you need to preserve status codes and headers, store a structured `{"status": 201, "headers": {...}, "body": {...}}` blob instead.

## When NOT to require the header

The endpoint must declare *required* idempotency via the dependency only when retries would cause damage. If you add `Depends(require_idempotency)` to every POST, clients will hate you and start putting the key into a constant. Reserve it for the dangerous endpoints — the ones the team explicitly identifies as "must not duplicate" — and document them in the API reference.

A reasonable starter set:

- All payment creation (supplier, customer, refund).
- Invoice creation (where invoice numbers are sequential and unique).
- Outbound message creation (push notification, email, SMS) — though many message providers have their own idempotency mechanism, in which case use *theirs* and don't double-up.

## Reviewing a PR that adds an endpoint

- [ ] Is this POST creating something with a real-world side effect (payment, message, booking)? If yes, does it require `Idempotency-Key`?
- [ ] Is the handler storing the response *after* commit?
- [ ] Is the cached payload going through the Pydantic schema, not the raw ORM object?
- [ ] Does the handler degrade open when Redis is unavailable?
- [ ] Are tests covering both paths: cache-miss (handler runs) and cache-hit (handler returns the cached payload)?
- [ ] Is a missing header returning 400, not 422 / 500?
- [ ] Is the dependency being misapplied to a GET or a naturally idempotent PATCH?

## Common failure modes

| Symptom | Likely cause |
|---|---|
| Two payments after a flaky network | Endpoint doesn't require `Idempotency-Key`, or client isn't sending one |
| First retry replays a stale response after the DB row changed | TTL too long, or the cached payload includes a field that's expected to be live |
| Idempotency cache fills Redis | TTL not set, or key namespace is scoped per request body hash (creating unbounded keys) |
| Replays return the wrong shape | Cache populated *before* commit; commit then failed and the row never existed |
| 422 errors on missing header confuse clients | Use 400 with a header-specific message |
| Two simultaneous requests with the same key both write | The race-window case; add a DB-level unique constraint or a Redis SETNX guard if it actually happens |

## Companion skills

- **`audit-log-pattern`** — log the *original* execution, not the replay. The first request audits; the replay returns the cached response without writing a second audit row.
- **`integration-resilience`** — if the mutation calls an outbound provider that has its own idempotency mechanism (Stripe, Square), forward your `Idempotency-Key` to them too.
