"""Purchase Order routes (admin-only writes)."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, get_current_user, require_admin
from app.schemas.schemas import POCreate, POOut
from app.services.po_service import PoService

po_router = APIRouter(prefix="/purchase-orders", tags=["purchase-order"])


@po_router.post("", response_model=POOut)
async def create_po(
    body: POCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """
    Create a standalone PurchaseOrder. POs exist independently of Bookings;
    they get attached to a Booking later via POST /bookings/{id}/purchase-orders.
    """
    return await PoService.create(db, body)


@po_router.patch("/{po_id}/submit")
async def submit_po(
    po_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    await PoService.submit(db, po_id, actor, get_client_ip(request))
    return {"message": "PO submitted"}


@po_router.get("/{po_id}", response_model=POOut)
async def get_po(
    po_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await PoService.get_for_actor(db, po_id, actor)
