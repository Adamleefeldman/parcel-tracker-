"""Customs clearance routes (UK agent writes per container)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, require_shipment_member
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.schemas.schemas import CustomsNoteCreate, CustomsRecordOut, CustomsUpdate
from app.services.customs_service import CustomsService

customs_router = APIRouter(
    prefix="/shipments/{shipment_id}/containers/{container_id}/customs", tags=["customs"]
)


@customs_router.put("", response_model=CustomsRecordOut)
async def upsert_customs(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: CustomsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    request: Request = None,
):
    return await CustomsService.upsert(
        db, shipment_id, container_id, body, actor, get_client_ip(request)
    )


@customs_router.post("/notes")
async def add_customs_note(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: CustomsNoteCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    await CustomsService.add_note(db, container_id, actor, body)
    result = {"message": "Note added"}
    await idempotency.store(result)
    return result
