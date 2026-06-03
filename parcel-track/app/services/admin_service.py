"""Admin read-only services backing the mobile Admin tab (People / System).

All methods are read-only and additive — no writes, no mutations. The existing
``AuthService.create_invite`` (POST /auth/invite) remains the only invite-write
path; nothing here touches it. Every method returns a ``PaginatedResponse``-shaped
dict ready for a route's ``response_model``.

NEVER serialise ``InviteToken.token_hash`` — ``InviteOut`` omits it entirely.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.db.models import AuditLog, InviteToken, User
from app.schemas.pagination import PaginationParams, paginate
from app.schemas.schemas import AuditLogOut, InviteOut

InviteStatus = Literal["pending", "used", "expired", "all"]


def _as_utc(dt: datetime) -> datetime:
    """Coerce a possibly-naive datetime to aware UTC.

    Postgres returns tz-aware datetimes; SQLite (local test fallback) returns
    naive ones. Normalising here keeps the ``expired`` comparison correct on
    both backends.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class AdminService:
    """Read-only list queries for users, invites, and the audit log."""

    @staticmethod
    async def list_users(
        db: AsyncSession,
        pagination: PaginationParams,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> dict:
        """List users (newest first) with optional role / active filters.

        Rows serialise directly to ``UserOut`` via ``response_model`` — no
        sensitive fields (``hashed_password``, ``expo_push_token``) are exposed.
        Role-breakdown counts are computed client-side from the returned list.
        """
        q: Select = select(User)
        if role is not None:
            q = q.where(User.role == role)
        if is_active is not None:
            q = q.where(User.is_active == is_active)
        q = q.order_by(User.created_at.desc())
        return await paginate(db, q, pagination)

    @staticmethod
    async def list_invites(
        db: AsyncSession,
        pagination: PaginationParams,
        *,
        status: InviteStatus = "pending",
    ) -> dict:
        """List invites, newest first, filtered by status.

        Pending = not used AND not yet expired. ``expired`` is derived per row;
        ``token_hash`` is never read into the response.
        """
        now = datetime.now(UTC)

        q: Select = select(InviteToken)
        if status == "pending":
            q = q.where(~InviteToken.used, InviteToken.expires_at > now)
        elif status == "used":
            q = q.where(InviteToken.used)
        elif status == "expired":
            q = q.where(~InviteToken.used, InviteToken.expires_at <= now)
        # "all" → no filter
        q = q.order_by(InviteToken.created_at.desc())

        rows = (
            (await db.execute(q.offset(pagination.offset).limit(pagination.limit))).scalars().all()
        )
        items = [
            InviteOut(
                id=inv.id,
                email=inv.email,
                role=inv.role.value,
                expires_at=inv.expires_at,
                created_at=inv.created_at,
                used=inv.used,
                expired=(not inv.used and _as_utc(inv.expires_at) <= now),
            )
            for inv in rows
        ]
        return await paginate(db, q, pagination, items=items)

    @staticmethod
    async def list_audit_logs(
        db: AsyncSession,
        pagination: PaginationParams,
        *,
        booking_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> dict:
        """Global audit-log feed, newest first, with the actor's name joined.

        The actor name comes from an explicit join on ``User`` (never lazy
        loading — that crashes in async). Optional ``booking_id`` / ``actor_id``
        filters are index-backed.
        """
        q: Select = select(AuditLog, User.name).join(User, User.id == AuditLog.actor_id)
        if booking_id is not None:
            q = q.where(AuditLog.booking_id == booking_id)
        if actor_id is not None:
            q = q.where(AuditLog.actor_id == actor_id)
        q = q.order_by(AuditLog.created_at.desc())

        rows = (await db.execute(q.offset(pagination.offset).limit(pagination.limit))).all()
        items = [
            AuditLogOut(
                id=log.id,
                created_at=log.created_at,
                actor_id=log.actor_id,
                actor_name=actor_name,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                old_value=log.old_value,
                new_value=log.new_value,
                ip_address=log.ip_address,
                booking_id=log.booking_id,
            )
            for log, actor_name in rows
        ]
        return await paginate(db, q, pagination, items=items)
