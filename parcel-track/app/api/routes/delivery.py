"""Delivery routes (admin loads points, UK agent schedules & updates status)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, require_admin, require_shipment_member
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.schemas import (
    DeliveryPointCreate,
    DeliveryPointOut,
    DeliveryScheduleCreate,
    DeliveryStatusUpdate,
)
from app.services.delivery_service import DeliveryService

delivery_router = APIRouter(prefix="/shipments/{shipment_id}/delivery", tags=["delivery"])


@delivery_router.post("/points", response_model=DeliveryPointOut)
async def create_delivery_point(
    shipment_id: uuid.UUID,
    body: DeliveryPointCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await DeliveryService.create_point(db, shipment_id, body)


@delivery_router.get("/points", response_model=PaginatedResponse[DeliveryPointOut])
async def list_delivery_points(
    shipment_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    return await DeliveryService.list_points(db, shipment_id, actor, pagination)


@delivery_router.post("/points/{point_id}/schedule")
async def schedule_delivery(
    shipment_id: uuid.UUID,
    point_id: uuid.UUID,
    body: DeliveryScheduleCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    resp = await DeliveryService.schedule(db, shipment_id, point_id, body, actor)
    await idempotency.store(resp)
    return resp


@delivery_router.patch("/points/{point_id}/status")
async def update_delivery_status(
    shipment_id: uuid.UUID,
    point_id: uuid.UUID,
    body: DeliveryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    idempotency: IdempotencyResult = Depends(require_idempotency),
    request: Request = None,
):
    if idempotency.cached_response:
        return idempotency.cached_response

    resp = await DeliveryService.update_status(
        db, shipment_id, point_id, body, actor, get_client_ip(request)
    )
    await idempotency.store(resp)
    return resp
