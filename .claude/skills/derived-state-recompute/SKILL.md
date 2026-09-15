---
name: derived-state-recompute
description: Use when designing or working with an entity status field whose value depends on multiple parallel events — payment tranches plus delivery plus customs plus disputes, or any combination where a strict transition graph would have too many edges to maintain. Triggers on phrases like "lifecycle status", "derived state", "computed status", "this depends on a bunch of things", "I can't model this as a clean state machine", "should this be a state machine or a calculation?", "recompute the status after X event", or when you see a status field being written from many different places in the codebase. Pairs with the `state-machine-service` skill — use whichever fits the domain.
---

# Derived-state recompute pattern

The companion to a strict state machine. When a status field depends on **multiple parallel events** rather than a single ordered hand-off, derive it from inputs instead of pushing it through transitions. The function that derives it is called `recompute(entity_id)`, and **every event writer** that could change one of its inputs calls it.

## State machine vs derived state — which to pick

| Symptom of the domain | Use |
|---|---|
| Status has one obvious "forward" direction and each step has a clear precondition | **state-machine-service** |
| Each transition is triggered by a single human or system action | **state-machine-service** |
| You want to *reject* a status change because preconditions aren't met | **state-machine-service** |
| Status reflects the combined state of several independent things (payment + delivery + dispute) | **derived-state-recompute** |
| Multiple events can race; the order is mostly determined by physical reality, not by a workflow | **derived-state-recompute** |
| Writing the transition graph by hand would mean enumerating combinations (delivered AND paid, delivered AND not paid, …) | **derived-state-recompute** |
| Two entities sit side-by-side: one is a strict funnel, one is "computed from a bag of events" | Use **both**; the funnel's terminal-state precondition reads the derived field |

The trap to avoid: forcing a derived-state domain into `VALID_TRANSITIONS`. Within months you'll have a transition table where every state can reach every other state. At that point the table no longer documents anything — it's a polite suggestion.

## The shape

1. **A `recompute(db, entity_id)` function** — reads the entity and its inputs in one query (or a small number of eager-loaded queries), derives a new status from them in a precedence-ordered chain of `if`s, writes it to the entity, returns the new value. Does not commit; the caller's transaction owns the surrounding write.
2. **Idempotency.** Calling `recompute` twice in a row yields the same value. No side effects beyond the status write itself.
3. **Call sites everywhere the inputs change.** Every event writer that could change one of the derivation inputs ends with `await Service.recompute(db, entity_id)` before its own commit. This is the social contract that keeps the field honest.
4. **A precedence rule** — when two derivation inputs both apply, exactly one wins. Documented at the top of `_derive` as a precedence-ordered list, so a reader knows the order matters.

## Canonical template

```python
# app/services/<entity>_lifecycle_service.py

class EntityLifecycleService:
    """Single entry point that recomputes <entity>.lifecycle_status from its
    concrete events.

    Inputs:
      - <event 1 field>  (e.g. vessel.atd / vessel.ata)
      - <event 2 field>  (e.g. customs_record.status)
      - <event 3 field>  (e.g. payment.banked_total vs target)
      - <side state field> (e.g. dispute_reason / disputed_at)

    Output: writes entity.lifecycle_status in place.

    Why a derivation function (not a state machine):
      <one or two sentences explaining what makes the domain "parallel events"
       rather than "ordered transitions". This docstring is the most important
       part of the file — readers come here to decide whether to keep using
       this pattern or migrate to a state machine.>

    When to call:
      After any write that changes one of the inputs.
    """

    @staticmethod
    async def recompute(db: AsyncSession, entity_id: UUID) -> Status:
        entity = await db.scalar(
            select(Entity)
            .where(Entity.id == entity_id)
            .options(selectinload(Entity.input_1),
                     selectinload(Entity.input_2))
        )
        if entity is None:
            # Deleted in the same transaction — nothing to do.
            return Status.INITIAL

        new_status = await EntityLifecycleService._derive(db, entity)
        entity.lifecycle_status = new_status
        return new_status

    @staticmethod
    async def _derive(db: AsyncSession, entity: Entity) -> Status:
        # ── Precedence (top of list wins): ─────────────────────────────
        # 1. DISPUTED side-state — overrides everything until cleared
        # 2. Financial leg — BANKED > PAID > INVOICED
        # 3. Operational leg — DELIVERED > CLEARED > IN_TRANSIT > ORDERED

        if entity.dispute_reason and entity.disputed_at:
            return Status.DISPUTED

        # Financial leg — compute from inputs, don't read a pushed flag
        banked, received, any_invoiced = await EntityLifecycleService._sums(db, entity.id)
        target = entity.sale_price_total or Decimal("0")
        if target > 0 and banked >= target:
            return Status.BANKED
        if received > 0:
            return Status.PAID
        if any_invoiced:
            return Status.INVOICED

        # Operational leg
        if await EntityLifecycleService._is_delivered(db, entity.id):
            return Status.DELIVERED
        if entity.customs_record and entity.customs_record.status == CustomsStatus.CLEARED:
            return Status.CLEARED
        if entity.vessel and entity.vessel.atd:
            return Status.IN_TRANSIT
        return Status.ORDERED

    @staticmethod
    async def recompute_for_parent(db: AsyncSession, parent_id: UUID) -> None:
        """Fan-out helper: recompute every child of a parent. Use after events
        that move multiple children at once (e.g. one vessel update affects
        every container on the same bill of lading)."""
        rows = await db.execute(select(Entity.id).where(Entity.parent_id == parent_id))
        for (cid,) in rows.all():
            await EntityLifecycleService.recompute(db, cid)
```

## Design rules — and why they matter

### Rule 1: Inputs only. Never read the field you're writing.

Inside `_derive`, never branch on the current value of `entity.lifecycle_status`. If you do, the function becomes order-dependent: the new value depends on the old value, which depends on the previous old value, and replaying events out of order produces different results. The whole reason to use this pattern is that you can replay it from scratch and get the same answer. Read the underlying events; ignore the field.

### Rule 2: Idempotent on purpose

Two consecutive calls must yield the same status. This is what makes "always call it after any event write" safe — duplicates, retries, and overlapping recomputes converge instead of fight. It's also what makes the function trivial to test: set up the inputs, call once, assert; call again, assert no change.

### Rule 3: Precedence is documented and short

The chain of `if`s is the entire spec. Keep it under ~10 branches; if it's longer, the domain is probably two derivations stacked, or it really is a state machine with extra steps. The top of `_derive` should have a numbered precedence comment so the reader knows the order is intentional.

### Rule 4: Call `recompute()` from every event writer, not from a global signal

Resist the temptation to install a SQLAlchemy `after_flush` or a Django `post_save` signal that "automatically" recomputes. Those fire silently, hide the call from the reader, and recurse when the recompute itself causes a write. Explicit calls at the event-writer site are easier to grep, easier to test, and easier to remove later.

### Rule 5: Don't commit inside `recompute`

Same rule as the state-machine service. The caller's transaction owns the unit of work. `recompute` is a building block.

### Rule 6: Handle the "deleted in the same transaction" case

If the entity row is gone (deleted by an earlier statement in the same transaction), return a sensible default instead of crashing. This is a real path — e.g. a bulk delete followed by a fan-out recompute.

### Rule 7: Use SQL `func.coalesce`, `func.sum`, etc. for sums — not Python loops

You're frequently summing payment tranches, delivery counts, or similar. Push these into one SQL aggregate query, not a Python loop after fetching every row. Keep the function fast enough that calling it on every event write is uncontroversial.

### Rule 8: When you need cross-dialect compatibility, prefer COUNT/CASE over `bool_or`

If the production DB is Postgres but the test suite uses SQLite, `bool_or` won't translate. The pattern `func.count(case((cond, 1)))` works on both. Worth the slightly less elegant SQL.

### Rule 9: Provide a fan-out helper when many siblings share an event

Vessel ETA updates affect every container under a bill of lading. Write `recompute_for_<parent>(db, parent_id)` so the event-writer can call one function instead of looping. Inside, that helper just iterates `recompute(db, child_id)` — keeping the per-child path the single source of truth.

## How this hooks into a sibling state machine

A common shape: one entity has a strict state machine (Booking), and its child has a derived lifecycle (Container). The Booking's terminal-state precondition reads the children's derived field:

```python
# inside Booking _check_preconditions for BookingStatus.COMPLETE:
pending = [c for c in containers if c.lifecycle_status not in {BANKED, CLOSED}]
if pending:
    raise HTTPException(400, f"{len(pending)} container(s) not yet banked")
```

That's how customer-paid bubbles up to close the booking — the state machine reads the derivation, and the derivation never reads the state machine. One-way dependency, no cycles.

## Reviewing a PR that touches a derived-state service

- [ ] Does the PR add a new derivation input? If so, is every event writer that mutates the new input updated to call `recompute()`?
- [ ] Does the PR add a new branch in `_derive`? If so, is its position in the precedence comment correct, and does it appear in the comment at all?
- [ ] Does any branch read the field being written? If yes, refactor — derive from inputs.
- [ ] Does `recompute` commit? If yes, remove the commit and let the caller own the transaction.
- [ ] Are there new event writers (background tasks, webhooks, admin endpoints) that *don't* call `recompute()`? They're a future drift bug.
- [ ] Is there a fan-out helper for the new input if it can affect multiple siblings?
- [ ] Tests: one test per branch in `_derive`. Idempotency test: call twice, assert no change.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| Status is stale after an event | An event writer forgot to call `recompute` |
| Status flickers between two values across calls | A branch reads the field it's writing |
| Order of saves matters in a test | Same as above — derivation is reading state instead of inputs |
| `recompute` is slow enough that nobody wants to call it | Too many round-trip queries; consolidate with `selectinload` and SQL aggregates |
| Two parallel writers produce inconsistent state | Add `SELECT … FOR UPDATE` on the entity row, or use serializable isolation, or accept eventual consistency and call `recompute` once more from a post-commit task |

## Companion skills

- **`state-machine-service`** — the strict-DAG sibling. Often used in the same codebase for the parent entity.
- **`audit-log-pattern`** — if you also want to record *why* the derived status changed, write an audit row in the event writer (not inside `recompute`).
