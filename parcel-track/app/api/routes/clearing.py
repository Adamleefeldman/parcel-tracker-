"""Clearing docs routes (UK agent writes)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import require_shipment_member
from app.schemas.schemas import ClearingDocsOut, ClearingDocsUpdate
from app.services.clearing_service import ClearingService

clearing_router = APIRouter(prefix="/shipments/{shipment_id}/clearing-docs", tags=["clearing-docs"])


@clearing_router.put("", response_model=ClearingDocsOut)
async def upsert_clearing_docs(
    shipment_id: uuid.UUID,
    body: ClearingDocsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    return await ClearingService.upsert(db, shipment_id, body, actor)
