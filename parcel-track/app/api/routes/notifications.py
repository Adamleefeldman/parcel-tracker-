"""Notification read and push-token routes."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Notification, User
from app.middleware.auth import get_current_user
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import NotificationOut

notif_router = APIRouter(prefix="/notifications", tags=["notifications"])


@notif_router.get("", response_model=PaginatedResponse[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    q = select(Notification).where(Notification.user_id == actor.id)
    if unread_only:
        q = q.where(~Notification.read)
    q = q.order_by(Notification.created_at.desc())
    return await paginate(db, q, pagination)


@notif_router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == actor.id
        )
    )
    notif = result.scalar_one_or_none()
    if notif:
        notif.read = True
    return {"message": "Marked as read"}


@notif_router.patch("/push-token")
async def register_push_token(
    token: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    actor.expo_push_token = token
    return {"message": "Push token registered"}
