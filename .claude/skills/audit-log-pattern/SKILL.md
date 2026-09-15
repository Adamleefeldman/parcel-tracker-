---
name: audit-log-pattern
description: Use whenever the user needs to track who did what to which entity in a backend system — compliance trails, security event logs, sensitive-mutation history, "who changed this field and when" investigations, or any audit / activity log. Triggers on phrases like "audit log", "audit trail", "activity log", "compliance log", "who changed X", "track sensitive mutations", "soc2 / hipaa / pci audit requirement", "before / after value", or "I need a record of every status change". Also use when reviewing code that inlines its own `db.add(AuditLog(...))` boilerplate in five places instead of going through a helper.
---

# Append-only audit log

A small, opinionated pattern for the cross-cutting `audit_logs` table that every serious backend ends up writing. The two ideas that travel:

1. **One append-only table, one helper, one schema** — used by state machines, auth, sensitive mutations, admin overrides. Don't sprawl it into per-feature audit tables.
2. **Write in the same transaction as the event you're auditing** — never as a side effect of a webhook, signal, or fire-and-forget task.

## Schema

```python
# app/db/models.py

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id          = Column(UUID, primary_key=True, default=uuid.uuid4)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # WHO
    actor_id    = Column(UUID, ForeignKey("users.id"), nullable=True, index=True)
    # nullable so background tasks / system actions are representable as actor_id IS NULL

    # WHAT
    action      = Column(String(64), nullable=False, index=True)
    # dotted convention: "booking.status_changed", "user.login", "container.dispute_opened"

    entity_type = Column(String(64), nullable=False, index=True)
    entity_id   = Column(UUID, nullable=False, index=True)
    # (entity_type, entity_id) is the join key. NOT a real FK — entities may be soft-deleted.

    # CONTEXT
    old_value   = Column(Text, nullable=True)   # JSON-encoded
    new_value   = Column(Text, nullable=True)   # JSON-encoded
    ip_address  = Column(String(64), nullable=True)
    request_id  = Column(String(64), nullable=True, index=True)
    # request_id lets you cross-reference one HTTP request to every audit row it produced

    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at_desc", created_at.desc()),
    )
```

**Database-level append-only enforcement** (Postgres):

```sql
-- Belt-and-braces protection against application bugs:
REVOKE UPDATE, DELETE ON audit_logs FROM <app_role>;
-- Migrations may need a different role for backfills; that's fine.
```

If your DB layer doesn't support per-table revokes, at minimum add a comment at the top of the model: `# APPEND-ONLY. Never UPDATE or DELETE rows here.`

## The write helper

The boilerplate `db.add(AuditLog(actor_id=..., action=..., entity_type=..., entity_id=..., old_value=json.dumps(...), new_value=json.dumps(...), ip_address=...))` will get re-implemented in ten places if you let it. Centralise:

```python
# app/services/audit_service.py

class AuditService:
    @staticmethod
    def record(
        db: AsyncSession,
        *,
        action: str,
        entity_type: str,
        entity_id: UUID,
        actor_id: UUID | None,
        old: dict | None = None,
        new: dict | None = None,
        ip: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Stage an audit row in the current session. Caller commits."""
        db.add(AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=json.dumps(old, default=str) if old is not None else None,
            new_value=json.dumps(new, default=str) if new is not None else None,
            ip_address=ip,
            request_id=request_id,
        ))
```

Note: `AuditService.record` is **not** async. It only stages a row in the session — no IO. Keep it sync so callers can use it without `await` and so it works equally well in sync/async contexts.

## Design rules — and why they matter

### Rule 1: Append-only. UPDATE and DELETE are bugs.

If a row is wrong, write a *new* row recording the correction. Mutating audit rows defeats the entire point of the table — the audit log is the place you go when "git blame on the database" isn't enough.

### Rule 2: Write in the same transaction as the event

`db.add(AuditLog(...))` belongs inside `transition_status`, inside the auth-success path, inside the admin-mutation handler — before the commit that persists the event. If the event rolls back, the audit row should roll back with it. Writing audit logs from a webhook or post-commit signal sounds clever and creates phantom rows when the event fails.

### Rule 3: Don't audit reads, audit *mutations*

Auditing every `GET /users/me` produces noise that drowns the signal. Audit:

- State transitions (state-machine service writes)
- Auth events (login, logout, token refresh, lockout, password reset)
- Sensitive mutations (role change, financial field edit, manual override)
- Admin override actions
- Bulk operations (the bulk itself, with a count — not every affected row)

Don't audit:

- Pagination, listings, view endpoints
- Heartbeats, health checks, metrics scrapes
- Routine retries of the same mutation (only audit the one that succeeded)

If the question "should this generate an audit row?" feels unclear, the answer is usually no.

### Rule 4: `action` is a dotted, low-cardinality enum-by-convention

`"booking.status_changed"`, `"user.login_succeeded"`, `"user.login_failed"`, `"container.dispute_opened"`. Don't put dynamic values in `action` — those go in `new_value`. Keep the verb past-tense ("changed", not "change") because audit rows record what already happened.

### Rule 5: `entity_type` + `entity_id` is the join key, not a real FK

A real FK forces the audit row to vanish when the entity does. That's the opposite of what you want — the audit history of a deleted entity is often the most valuable kind. Use `(entity_type, entity_id)` so the row outlives its subject.

### Rule 6: Use `request_id` for cross-row correlation

If your request middleware sets a request-id contextvar (see the `fastapi-middleware-stack` skill), pull it into the audit row. One HTTP request that triggers four mutations gets four audit rows sharing the same `request_id` — investigation becomes a single query.

### Rule 7: JSON-encode old/new values; don't normalize them into separate columns

The temptation is to add `old_status`, `new_status`, `old_amount`, `new_amount` columns per audited field. Resist it — every new auditable field becomes a migration. JSON in `old_value` / `new_value` keeps the schema stable, and Postgres `jsonb` (if you upgrade the column) makes querying tractable later.

### Rule 8: Use a trusted-proxy-aware IP resolver

Don't trust `X-Forwarded-For` blindly — only honour it when the direct peer is on the trusted-proxy allowlist. Use the same resolver you use for rate-limiting so an audit log entry and a rate-limit decision agree on who the client is.

### Rule 9: Don't put PII you can avoid

`new_value` containing `{"email": "alice@example.com"}` is a 7-year retention liability. If the audit story doesn't actually need it, omit it or reference by user_id only.

### Rule 10: Indexing

`(entity_type, entity_id)` composite index for "history of this entity" queries. `created_at desc` index for "what happened recently" queries. Don't index `action` unless you actually query by it; cardinality is low enough that a sequential scan over a partition is fine.

## Usage examples

### From a state-machine transition

```python
old_status = entity.status
entity.status = new_status
AuditService.record(
    db,
    action="entity.status_changed",
    entity_type="entity",
    entity_id=entity.id,
    actor_id=actor.id,
    old={"status": old_status.value},
    new={"status": new_status.value},
    ip=ip,
    request_id=request_id_ctx.get(),
)
```

### From an auth event

```python
AuditService.record(
    db,
    action="user.login_succeeded",
    entity_type="user",
    entity_id=user.id,
    actor_id=user.id,         # self-action
    ip=client_ip,
    request_id=request_id_ctx.get(),
)
```

### From an admin override

```python
AuditService.record(
    db,
    action="booking.admin_override_status",
    entity_type="booking",
    entity_id=booking.id,
    actor_id=admin.id,
    old={"status": old.value},
    new={"status": new.value, "reason": justification},
    ip=ip,
)
```

## Reviewing a PR that touches the audit log

- [ ] Are audit writes inside the same transaction as the event they describe?
- [ ] Is anyone calling `UPDATE audit_logs` or `DELETE FROM audit_logs`? If yes, hard stop — find the alternative.
- [ ] Are dynamic values being concatenated into `action`? Move them to `new_value`.
- [ ] Are we auditing reads? If yes, push back unless there's a regulatory reason.
- [ ] Are old/new values being normalized into new columns? Push back — JSON column, stable schema.
- [ ] Is the IP being resolved through the trusted-proxy helper, not `request.client.host` blindly?
- [ ] Does the request-id propagate so multi-row events stay correlatable?

## Common failure modes

| Symptom | Likely cause |
|---|---|
| Audit rows exist for events that didn't happen | Audit write is in a post-commit hook or webhook handler; original transaction rolled back |
| Audit rows missing for some transitions | A route handler is writing the status field directly, bypassing the service |
| Audit log fills disk fast | You're auditing reads, or pagination, or both — restrict to mutations |
| Can't tell which audit rows belong to one HTTP request | `request_id` not propagated; add it to the audit row via the request-logging middleware contextvar |
| Audit row references a deleted entity, IDE shows broken FK | You used a real FK; remove it and use `(entity_type, entity_id)` instead |

## Companion skills

- **`state-machine-service`** — the primary caller of `AuditService.record` for status transitions.
- **`derived-state-recompute`** — when a derived status changes, audit the *event* that caused the recompute, not the recompute itself.
- **`fastapi-middleware-stack`** — for the request-id contextvar that ties multi-row events together.
