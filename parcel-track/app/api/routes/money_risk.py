"""Money-risk dashboard route (mobile Phase 10).

A single read-only endpoint aggregating A/R aging exposure, demurrage
countdowns, and dispute counts — the data behind the mobile "Alerts" tab.
Gated to the roles that already receive these alerts (ADMIN + UK_AGENT);
Morocco agent and customer get 403.

Read-only and additive — no migrations, no model changes. All money fields are
``Decimal`` and serialise to JSON strings under ``response_model``.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import require_role
from app.schemas.money_risk import MoneyRiskOut
from app.services.money_risk_service import MoneyRiskService

money_risk_router = APIRouter(prefix="/money-risk", tags=["money-risk"])


@money_risk_router.get("", response_model=MoneyRiskOut)
async def get_money_risk(
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN, UserRole.UK_AGENT)),
) -> MoneyRiskOut:
    """A/R aging buckets, demurrage countdowns, and dispute counts in one call.

    Aging is measured from ``Container.updated_at`` (approximate — no precise
    ``delivered_at`` yet) and demurrage countdowns are whole-day (``Vessel.ata``
    is a date). Outstanding £ is the full sale value of unbanked containers, not
    netted against banked tranches.
    """
    return await MoneyRiskService.summary(db)
