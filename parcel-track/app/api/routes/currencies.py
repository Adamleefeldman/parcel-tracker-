"""Currency master routes (Data-Foundation Pillar 1a).

The `currencies` reference table (spec §2.2). Any authenticated user can list
(currencies feed pickers and FX conversion); admin-only for create/update.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_client_ip, get_current_user, require_admin
from app.schemas.schemas import CurrencyCreate, CurrencyOut, CurrencyUpdate
from app.services.currency_service import CurrencyService

currency_router = APIRouter(prefix="/currencies", tags=["currencies"])


@currency_router.get("", response_model=list[CurrencyOut])
async def list_currencies(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await CurrencyService.list_all(db, active_only=active_only)


@currency_router.post("", response_model=CurrencyOut)
async def create_currency(
    body: CurrencyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await CurrencyService.create(db, body, actor, get_client_ip(request))


@currency_router.patch("/{code}", response_model=CurrencyOut)
async def update_currency(
    code: str,
    body: CurrencyUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await CurrencyService.update(db, code, body, actor, get_client_ip(request))
