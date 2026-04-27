"""Purchase Order routes (admin-only writes)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, require_admin, require_shipment_member
from app.schemas.schemas import POCreate, POOut
from app.services.po_service import PoService

po_router = APIRouter(prefix="/shipments/{shipment_id}/po", tags=["purchase-order"])


@po_router.post("", response_model=POOut)
async def create_po(
    shipment_id: uuid.UUID,
    body: POCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await PoService.create(db, shipment_id, body)


@po_router.patch("/{po_id}/submit")
async def submit_po(
    shipment_id: uuid.UUID,
    po_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    request: Request = None,
):
    await PoService.submit(db, shipment_id, po_id, actor, get_client_ip(request))
    return {"message": "PO submitted"}


@po_router.get("")
async def get_po(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    return await PoService.get_for_actor(db, shipment_id, actor)
