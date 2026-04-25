"""Clearing docs routes (UK agent writes)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ClearingDocsStatus, UserRole
from app.db.database import get_db
from app.db.models import ClearingDocs, User
from app.middleware.auth import require_shipment_member
from app.schemas.schemas import ClearingDocsOut, ClearingDocsUpdate

clearing_router = APIRouter(prefix="/shipments/{shipment_id}/clearing-docs", tags=["clearing-docs"])


@clearing_router.put("", response_model=ClearingDocsOut)
async def upsert_clearing_docs(
    shipment_id: uuid.UUID,
    body: ClearingDocsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Only admin or UK agent can update clearing docs")

    result = await db.execute(select(ClearingDocs).where(ClearingDocs.shipment_id == shipment_id))
    docs = result.scalar_one_or_none()

    if not docs:
        docs = ClearingDocs(shipment_id=shipment_id, uploaded_by=actor.id)
        db.add(docs)
        await db.flush()

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(docs, field, value)

    required = [docs.has_customs_entry, docs.has_packing_list, docs.has_certificate_of_origin]
    if all(required):
        docs.status = ClearingDocsStatus.COMPLETE
    elif any(required):
        docs.status = ClearingDocsStatus.PARTIAL

    return docs
