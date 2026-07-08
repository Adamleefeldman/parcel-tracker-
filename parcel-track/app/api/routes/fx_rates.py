"""FX-rate routes (Data-Foundation Pillar 1b).

Read-only history + latest rates for any authenticated user. Writes happen only
via the ExchangeRate-API beat job (`poll_fx_rates`) — there is no write endpoint.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_current_user
from app.schemas.schemas import FxRateOut
from app.services.fx_service import FxService

fx_rate_router = APIRouter(prefix="/fx-rates", tags=["fx-rates"])


@fx_rate_router.get("", response_model=list[FxRateOut])
async def list_fx_rates(
    quote: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await FxService.list_rates(db, quote=quote, limit=limit)


@fx_rate_router.get("/latest", response_model=list[FxRateOut])
async def latest_fx_rates(
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await FxService.latest_per_quote(db)
