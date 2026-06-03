"""Admin read-only routes backing the mobile Admin tab (People / System).

Three list endpoints — users, invites, audit log — all gated to ADMIN and all
read-only. No mutations live here: the existing ``POST /auth/invite`` remains the
only invite-write path (mobile sends invites through it). View + send-invites
scope only; revoke/deactivate/role-change are deliberately out of scope.

Routes (note for mobile types):
    GET /api/v1/users        → PaginatedResponse[UserOut]
    GET /api/v1/invites      → PaginatedResponse[InviteOut]   (token_hash never exposed)
    GET /api/v1/audit-logs   → PaginatedResponse[AuditLogOut]
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import require_admin
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.schemas import AuditLogOut, InviteOut, UserOut
from app.services.admin_service import AdminService, InviteStatus

admin_router = APIRouter(tags=["admin"])


@admin_router.get("/users", response_model=PaginatedResponse[UserOut])
async def list_users(
    role: UserRole | None = None,
    is_active: bool | None = None,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """List users (newest first). Optional ``role`` / ``is_active`` filters.

    Role-breakdown counts are computed client-side from the returned page.
    """
    return await AdminService.list_users(db, pagination, role=role, is_active=is_active)


@admin_router.get("/invites", response_model=PaginatedResponse[InviteOut])
async def list_invites(
    status: InviteStatus = "pending",
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """List invites, newest first. ``status`` ∈ pending|used|expired|all
    (default ``pending``). ``token_hash`` is never serialised."""
    return await AdminService.list_invites(db, pagination, status=status)


@admin_router.get("/audit-logs", response_model=PaginatedResponse[AuditLogOut])
async def list_audit_logs(
    booking_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Global audit-log feed, newest first. Optional ``booking_id`` /
    ``actor_id`` filters. ``actor_name`` is joined from ``User``."""
    return await AdminService.list_audit_logs(
        db, pagination, booking_id=booking_id, actor_id=actor_id
    )
