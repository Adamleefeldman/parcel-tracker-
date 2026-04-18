from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.redis import (
    clear_login_failures,
    get_lockout_ttl,
    increment_login_failure,
    is_login_locked,
)
from app.core.security import (
    create_access_token,
    create_invite_token,
    create_refresh_token,
    hash_password,
    hash_token,
    invite_token_expiry,
    refresh_token_expiry,
    verify_password,
)
from app.db.models import InviteToken, RefreshToken, ShipmentUser, User
from app.schemas.schemas import (
    AcceptInviteRequest,
    InviteRequest,
    LoginRequest,
    TokenResponse,
)


class AuthService:
    @staticmethod
    async def create_invite(
        db: AsyncSession,
        request: InviteRequest,
        actor: User,
    ) -> dict:
        """Admin-only: create a time-limited invite token for a new user."""
        raw_token, token_hash = create_invite_token()

        invite = InviteToken(
            token_hash=token_hash,
            email=request.email,
            role=UserRole(request.role),
            shipment_id=request.shipment_id,
            created_by=actor.id,
            expires_at=invite_token_expiry(),
        )
        db.add(invite)
        await db.flush()

        return {
            "invite_token": raw_token,
            "email": request.email,
            "expires_at": invite.expires_at,
        }

    @staticmethod
    async def accept_invite(
        db: AsyncSession,
        request: AcceptInviteRequest,
    ) -> TokenResponse:
        """Accept an invite, create the user account, and return auth tokens."""
        token_hash = hash_token(request.token)

        result = await db.execute(
            select(InviteToken).where(
                InviteToken.token_hash == token_hash,
                ~InviteToken.used,
            )
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or already used invite token",
            )
        invite_expires = (
            invite.expires_at if invite.expires_at.tzinfo else invite.expires_at.replace(tzinfo=UTC)
        )
        if invite_expires < datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token has expired"
            )

        # Check email not already registered
        existing = await db.execute(select(User).where(User.email == invite.email))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
            )

        user = User(
            email=invite.email,
            hashed_password=hash_password(request.password),
            name=request.name,
            role=invite.role,
        )
        db.add(user)
        await db.flush()

        # If invite is tied to a shipment, add membership automatically
        if invite.shipment_id:
            membership = ShipmentUser(
                shipment_id=invite.shipment_id,
                user_id=user.id,
            )
            db.add(membership)

        invite.used = True

        access_token = create_access_token(str(user.id), user.role)
        raw_refresh, refresh_hash = create_refresh_token()

        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=refresh_hash,
                expires_at=refresh_token_expiry(),
            )
        )

        return {
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "token_type": "bearer",
        }

    @staticmethod
    async def login(
        db: AsyncSession,
        request: LoginRequest,
    ) -> dict:
        settings = get_settings()

        if await is_login_locked(request.email, settings.LOGIN_MAX_ATTEMPTS):
            retry_after = await get_lockout_ttl(request.email)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked due to too many failed login attempts",
                headers={"Retry-After": str(retry_after)},
            )

        result = await db.execute(select(User).where(User.email == request.email, User.is_active))
        user = result.scalar_one_or_none()

        if not user or not verify_password(request.password, user.hashed_password):
            count = await increment_login_failure(
                request.email, settings.LOGIN_LOCKOUT_WINDOW_SECONDS
            )
            if count >= settings.LOGIN_MAX_ATTEMPTS:
                retry_after = await get_lockout_ttl(request.email)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Account temporarily locked due to too many failed login attempts",
                    headers={"Retry-After": str(retry_after)},
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        await clear_login_failures(request.email)
        access_token = create_access_token(str(user.id), user.role)
        raw_refresh, refresh_hash = create_refresh_token()

        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=refresh_hash,
                expires_at=refresh_token_expiry(),
            )
        )

        return {
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "token_type": "bearer",
        }

    @staticmethod
    async def refresh(db: AsyncSession, raw_refresh: str) -> dict:
        token_hash = hash_token(raw_refresh)

        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                ~RefreshToken.revoked,
            )
        )
        token_record = result.scalar_one_or_none()

        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )
        token_expires = (
            token_record.expires_at
            if token_record.expires_at.tzinfo
            else token_record.expires_at.replace(tzinfo=UTC)
        )
        if token_expires < datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired"
            )

        # Rotate: revoke old, issue new
        token_record.revoked = True

        user_result = await db.execute(
            select(User).where(User.id == token_record.user_id, User.is_active)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        access_token = create_access_token(str(user.id), user.role)
        raw_new, new_hash = create_refresh_token()

        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=new_hash,
                expires_at=refresh_token_expiry(),
            )
        )

        return {
            "access_token": access_token,
            "refresh_token": raw_new,
            "token_type": "bearer",
        }

    @staticmethod
    async def revoke_refresh(db: AsyncSession, raw_refresh: str) -> None:
        token_hash = hash_token(raw_refresh)
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        token_record = result.scalar_one_or_none()
        if token_record:
            token_record.revoked = True
