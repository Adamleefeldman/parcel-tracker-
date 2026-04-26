"""Authentication routes: invite, accept-invite, login, refresh, logout."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RATE_LIMIT_AUTH, RATE_LIMIT_INVITE, RATE_LIMIT_REFRESH
from app.core.redis import revoke_access_token
from app.core.security import decode_access_token
from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_current_user, require_admin
from app.middleware.rate_limit import limiter
from app.schemas.schemas import AcceptInviteRequest, InviteRequest, LoginRequest, RefreshRequest
from app.services.auth_service import AuthService

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/invite")
@limiter.limit(RATE_LIMIT_INVITE)
async def create_invite(
    request: Request,
    body: InviteRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await AuthService.create_invite(db, body, actor)


@auth_router.post("/accept-invite")
@limiter.limit(RATE_LIMIT_INVITE)
async def accept_invite(
    request: Request,
    body: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
):
    return await AuthService.accept_invite(db, body)


@auth_router.post("/login")
@limiter.limit(RATE_LIMIT_AUTH)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    return await AuthService.login(db, body)


@auth_router.post("/refresh")
@limiter.limit(RATE_LIMIT_REFRESH)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    return await AuthService.refresh(db, body.refresh_token)


_bearer = HTTPBearer(auto_error=False)


@auth_router.post("/logout")
@limiter.limit(RATE_LIMIT_REFRESH)
async def logout(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    await AuthService.revoke_refresh(db, body.refresh_token)

    if credentials:
        payload = decode_access_token(credentials.credentials)
        if payload and (jti := payload.get("jti")):
            exp = payload.get("exp", 0)
            remaining_ttl = max(1, int(exp - datetime.now(UTC).timestamp()))
            await revoke_access_token(jti, remaining_ttl)

    return {"message": "Logged out"}
