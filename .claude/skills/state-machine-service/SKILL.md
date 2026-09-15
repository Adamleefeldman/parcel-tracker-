---
name: state-machine-service
description: Use when adding, modifying, or auditing a workflow status / state field on a database entity (Order, Booking, Ticket, Onboarding, Dispute, Subscription, Document, etc.) where transitions must respect a defined order. Triggers on phrases like "state machine", "status transitions", "workflow status", "advance to X state", "move to next stage", "approve/reject flow", "lifecycle status", or "what statuses can this go to next". Also use when reviewing code that writes `entity.status = …` directly from a route handler — that's the anti-pattern this skill exists to prevent.
---

# Funnel-style state-machine service

This skill describes a battle-tested pattern for entity state transitions in a Python/FastAPI codebase (the principles generalize cleanly to Django, Rails, Express, etc.).

## When this pattern fits

Use it when **all** of the following hold:

1. The entity has a discrete `status` enum.
2. Transitions form a (mostly) directed graph with a clear "forward" direction — orders, applications, approvals, shipments, kyc flows, etc.
3. Each target state has **preconditions** (other rows must exist, other amounts must reconcile, other statuses must be reached).
4. You want a single audit trail for "who moved this and when."

If the status is more like a **derived projection** of many parallel events (a customer payment that has tranches, variance, and batched invoicing — see the companion `derived-state-recompute` skill), use that pattern instead. Don't try to force parallel-event domains into a strict DAG; you'll write transition rules that contradict each other within six months.

## The shape

Every state-machine service in this style has four parts:

1. **A `VALID_TRANSITIONS` table** — a plain dict mapping each state to the list of states it can advance to. Terminal states map to `[]`. This is the *only* place the graph lives.
2. **A `transition_status(entity, new_status, actor, ip)` function** — the single public entry point. Everything that wants to change the status calls this. Nothing else may write the field.
3. **Per-target precondition checks** — branched on the target state, raising a structured 400 with a human-readable reason when unmet.
4. **An audit-log write** — append a row recording actor, action, entity, old value, new value, ip. Don't commit inside the service; let the caller's transaction wrap the whole change.

The invariant that makes this pattern hold up over time is: **route handlers, background tasks, signals, and tests never write `entity.status = …` directly.** They call `transition_status`. Enforce it socially (code review, CLAUDE.md note) — there's no language-level way to lock the attribute.

## Canonical template

```python
# app/services/<entity>_service.py

VALID_TRANSITIONS: dict[Status, list[Status]] = {
    Status.DRAFT:           [Status.SUBMITTED],
    Status.SUBMITTED:       [Status.UNDER_REVIEW, Status.REJECTED],
    Status.UNDER_REVIEW:    [Status.APPROVED, Status.REJECTED],
    Status.APPROVED:        [Status.ACTIVE],
    Status.ACTIVE:          [Status.CLOSED],
    Status.REJECTED:        [],   # terminal
    Status.CLOSED:          [],   # terminal
}


class EntityService:
    @staticmethod
    async def transition_status(
        db: AsyncSession,
        entity: Entity,
        new_status: Status,
        actor: User,
        ip: str | None = None,
    ) -> Entity:
        """Single gate. Validates the edge, checks preconditions, writes audit log."""
        current = entity.status
        if new_status not in VALID_TRANSITIONS.get(current, []):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{current}' to '{new_status}'",
            )

        await EntityService._check_preconditions(db, entity, new_status)

        old_status = entity.status
        entity.status = new_status

        db.add(AuditLog(
            actor_id=actor.id,
            action="entity.status_changed",
            entity_type="entity",
            entity_id=entity.id,
            old_value=json.dumps({"status": old_status.value}),
            new_value=json.dumps({"status": new_status.value}),
            ip_address=ip,
        ))
        return entity

    @staticmethod
    async def _check_preconditions(
        db: AsyncSession, entity: Entity, target: Status
    ) -> None:
        if target == Status.SUBMITTED:
            if not entity.submitted_document_id:
                raise HTTPException(400, "Document must be uploaded before submitting")

        elif target == Status.APPROVED:
            # Walk whatever join chain the rule actually requires.
            paid = await db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0))
                .where(Payment.entity_id == entity.id, Payment.status == "CONFIRMED")
            )
            if paid < entity.total_due:
                raise HTTPException(
                    400, f"Payments ({paid}) do not cover total due ({entity.total_due})"
                )
        # … one branch per target with non-trivial preconditions
```

## Design rules — and why they matter

### Rule 1: One transitions table, defined statically at module level

Don't compute it at runtime, don't spread it across classes, don't read it from the DB. The graph is the contract — a reader should be able to take in the whole legal flow at a glance. Putting it anywhere else makes "what statuses can this reach next?" an investigation instead of a glance.

### Rule 2: The service writes the field. Routes never do.

The whole point of the pattern collapses if any other code can mutate `entity.status`. When that happens, you get transitions without preconditions, transitions without audit rows, and transitions that bypass the graph. Within months, the table becomes a polite suggestion and the service becomes "the slow path some endpoints use." Treat direct `entity.status = …` writes outside the service as a code review red flag everywhere except in migrations or in a deliberate, commented backfill.

### Rule 3: Preconditions raise structured errors, not assertions

When a precondition fails, the user (or the upstream system) needs to know *why* — "Invoice must be uploaded before proceeding", "Payments do not cover total invoice value (1,200 < 1,500)". A bare `assert` or generic 400 loses that. The error message is part of the API contract.

### Rule 4: Write the audit row in the same transaction

If the status mutation commits and the audit row doesn't, you've corrupted the audit trail. Stage both with `db.add(...)` inside the service and let the caller's `db.commit()` (or rollback) cover them together. Don't `await db.commit()` inside the service — it's a building block, not an endpoint.

### Rule 5: Don't model side-effects (emails, webhooks) inside `transition_status`

Trigger them *after* the commit, ideally via an outbox table or a background task enqueue keyed on the audit-log row. If you send a webhook from inside the transition function and the transaction rolls back, you've leaked a phantom event.

### Rule 6: Terminal states map to `[]`, not absent keys

`COMPLETE: []` documents the intent. A missing key (using `.get(current, [])`) makes "is this state terminal or did someone forget to add it?" ambiguous.

### Rule 7: Walk the real join chain in preconditions

If a Booking aggregates many POs and each PO has one Invoice and many Payments, then "all paid" means walking `Booking → BookingPurchaseOrder → PurchaseOrder → Invoice → Payment`. Don't take shortcuts that only work in the 1:1 case — they silently fail on multi-PO bookings.

### Rule 8: Don't add a "force" parameter

A `force=True` kwarg that bypasses preconditions starts life as a convenience for one admin script and ends as the way half the codebase moves status. If you need an admin override, build a separate explicit endpoint that writes its own audit-log reason ("admin_override: <justification>") and let it call `transition_status` on a reduced graph — or write the field with a clearly named `admin_override_status` helper that is itself audited.

## Reviewing a PR that touches a state machine

Walk this checklist:

- [ ] Does the PR add or change a state? If so, is `VALID_TRANSITIONS` updated, and does every edge it adds make sense in both directions (can this state actually be reached; can it actually leave)?
- [ ] Does any new code write `entity.status = …` outside the service? If yes, push back — route the write through `transition_status`.
- [ ] For each new target state, is there a precondition branch, even an empty one with a comment "no preconditions, this is purely admin-driven"?
- [ ] Does the precondition use database-current data (re-query inside the transaction) or stale in-memory data passed in?
- [ ] Is the audit-log row added in the same transaction as the status write?
- [ ] Are emails / webhooks / push notifications dispatched *after* the commit (outbox, post-commit hook, or background task), not inside the transition?
- [ ] Tests: at least one test per new edge, at least one test per new precondition failure mode.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| "It works locally, breaks in CI" on multi-row preconditions | A test fixture has one PO/payment/etc.; the precondition only handles the 1:1 case |
| Audit log has gaps for some transitions | A route is writing the field directly and bypassing the service |
| Status "flickers" — moves forward then back | A background task is racing with a user action; neither is using a row-level lock or a `WHERE status = expected` guard |
| New developer asks "why isn't this advancing?" | Precondition error message is too generic — improve the wording before adding docs |
| A status got added to the enum but no transitions wire to it | `VALID_TRANSITIONS` wasn't updated; the state is unreachable |

## Companion skills

- **`derived-state-recompute`** — for status fields driven by parallel events instead of strict edges. Often coexists in the same codebase: one entity has a strict state machine and references a related entity whose status is derived.
- **`audit-log-pattern`** — defines the table this skill writes to.
