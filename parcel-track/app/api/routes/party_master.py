"""Party master routes (Data-Foundation Pillar 3).

The `parties` reference table (spec §4) — suppliers and every non-customer
counterparty, with bank accounts and default terms. Any authenticated user can
read (parties feed pickers, supplier payments and the partner portal); admin
only for create/update and bank-account writes. Customers/brokers stay on the
separate `/brokers` + `/companies` routes (spec §4 non-goal).
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PartyType
from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, get_current_user, require_admin
from app.schemas.schemas import (
    FreeZoneWatchOut,
    PartyBankAccountCreate,
    PartyBankAccountOut,
    PartyCreate,
    PartyOut,
    PartyUpdate,
)
from app.services.party_service import PartyService

party_router = APIRouter(prefix="/parties", tags=["parties"])


@party_router.get("", response_model=list[PartyOut])
async def list_parties(
    party_type: PartyType | None = Query(None, alias="type"),
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await PartyService.list_all(db, party_type=party_type, active_only=active_only)


@party_router.get("/free-zone-watch", response_model=list[FreeZoneWatchOut])
async def free_zone_watch(
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await PartyService.free_zone_watch(db)


@party_router.post("", response_model=PartyOut)
async def create_party(
    body: PartyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await PartyService.create(db, body, actor, get_client_ip(request))


@party_router.get("/{party_id}", response_model=PartyOut)
async def get_party(
    party_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await PartyService.get_or_404(db, party_id)


@party_router.patch("/{party_id}", response_model=PartyOut)
async def update_party(
    party_id: uuid.UUID,
    body: PartyUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await PartyService.update(db, party_id, body, actor, get_client_ip(request))


@party_router.post("/{party_id}/bank-accounts", response_model=PartyBankAccountOut)
async def add_bank_account(
    party_id: uuid.UUID,
    body: PartyBankAccountCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await PartyService.add_bank_account(db, party_id, body, actor, get_client_ip(request))
