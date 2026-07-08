"""Legal-entity master routes (Data-Foundation Pillar 2).

The `legal_entities` reference table (spec §3) — the multi-entity tag every
transaction carries. Any authenticated user can list (entities feed pickers and
reporting filters); admin-only for create/update.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, get_current_user, require_admin
from app.schemas.schemas import LegalEntityCreate, LegalEntityOut, LegalEntityUpdate
from app.services.legal_entity_service import LegalEntityService

legal_entity_router = APIRouter(prefix="/legal-entities", tags=["legal-entities"])


@legal_entity_router.get("", response_model=list[LegalEntityOut])
async def list_legal_entities(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await LegalEntityService.list_all(db, active_only=active_only)


@legal_entity_router.post("", response_model=LegalEntityOut)
async def create_legal_entity(
    body: LegalEntityCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await LegalEntityService.create(db, body, actor, get_client_ip(request))


@legal_entity_router.patch("/{entity_id}", response_model=LegalEntityOut)
async def update_legal_entity(
    entity_id: uuid.UUID,
    body: LegalEntityUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await LegalEntityService.update(db, entity_id, body, actor, get_client_ip(request))
