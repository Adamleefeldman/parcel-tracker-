"""
Auth & permission middleware.

Every protected route depends on `get_current_user`.
Shipment-scoped routes additionally call `require_shipment_access`.
Financial data is stripped via `financial_fields_allowed`.
"""

import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.network import get_client_ip as _resolve_client_ip
from app.core.redis import is_token_revoked
from app.core.security import decode_access_token
from app.db.database import get_db
from app.db.models import ShipmentUser, User

bearer_scheme = HTTPBearer(auto_error=False)


# ── Token extraction + user lookup ────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )

    # Check server-side revocation (set on logout)
    jti = payload.get("jti")
    if jti and await is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked"
        )

    user_id = payload.get("sub")
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from None

    result = await db.execute(select(User).where(User.id == user_uuid, User.is_active))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or deactivated"
        )

    return user


# ── Role guards ───────────────────────────────────────────────────────────────


def require_role(*roles: UserRole):
    """Dependency factory: raises 403 if the current user's role is not in the allowed set."""

    async def check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return current_user

    return check


require_admin = require_role(UserRole.ADMIN)


# ── Shipment-scoped access ────────────────────────────────────────────────────


async def get_shipment_member(
    shipment_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> ShipmentUser:
    """
    Checks that the current user is a member of the given shipment.
    Returns the ShipmentUser record (which carries the effective role).
    Admins are always granted access.
    """
    if current_user.role == UserRole.ADMIN:
        # Admins see all shipments — return a synthetic membership
        return _AdminMembership(current_user)

    result = await db.execute(
        select(ShipmentUser).where(
            ShipmentUser.shipment_id == shipment_id,
            ShipmentUser.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No access to this shipment"
        )

    return membership


class _AdminMembership:
    """Synthetic membership for admins — has full effective_role."""

    def __init__(self, user: User):
        self.user = user
        self.role_override = None

    @property
    def effective_role(self) -> UserRole:
        return UserRole.ADMIN


async def require_shipment_member(
    shipment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency: verifies the current user is a member of the shipment (any role).
    Admins bypass the check automatically via _AdminMembership.
    Returns the User so route handlers need no signature changes.
    """
    await get_shipment_member(shipment_id, current_user, db)
    return current_user


def require_shipment_role(*roles: UserRole):
    """
    Dependency factory for shipment-scoped routes.
    Usage: Depends(require_shipment_role(UserRole.ADMIN, UserRole.UK_AGENT))
    """

    async def check(
        shipment_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> tuple[User, ShipmentUser]:
        membership = await get_shipment_member(shipment_id, current_user, db)
        if membership.effective_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this shipment action",
            )
        return current_user, membership

    return check


# ── Financial field guard ─────────────────────────────────────────────────────


def financial_fields_allowed(current_user: User) -> bool:
    """
    Only admins see financial amounts (PO value, invoice value, payment amounts).
    Agents and customers receive None for these fields.
    This is enforced in the service layer before serialisation.
    """
    return current_user.role == UserRole.ADMIN


# ── Audit log helper (request context) ───────────────────────────────────────


def get_client_ip(request: Request) -> str | None:
    """
    Resolve the client IP for audit logging.

    Uses the shared trusted-proxy-aware resolution so audit logs record
    the same IP as the rate limiter — prevents XFF spoofing in audit trails.
    """
    settings = get_settings()
    return _resolve_client_ip(request, settings.is_production, settings.TRUSTED_PROXIES)
