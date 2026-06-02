"""Money-risk dashboard facade (mobile Phase 10).

Composes the three read-only aggregations the dashboard needs into a single
response:

  * A/R aging   — :meth:`ARagingService.summary`
  * Demurrage   — :meth:`DemurrageService.countdown`
  * Disputes    — two ``COUNT`` queries over ``Container``

Read-only and additive: no migrations, no model changes. The existing
``run()`` alerters on the A/R and demurrage services are left untouched — these
methods only read.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ContainerLifecycleStatus
from app.db.models import Container
from app.schemas.money_risk import DisputeSummary, MoneyRiskOut
from app.services.ar_aging_service import ARagingService
from app.services.demurrage_service import DemurrageService


class MoneyRiskService:
    @staticmethod
    async def _disputes(db: AsyncSession) -> DisputeSummary:
        """Count disputed containers, split by whether an admin has acknowledged
        the dispute. Lifecycle stays ``DISPUTED`` either way (history is
        preserved); acknowledgement only lifts the booking-completion blocker."""
        base = select(func.count()).where(
            Container.lifecycle_status == ContainerLifecycleStatus.DISPUTED
        )
        unacknowledged = await db.scalar(base.where(Container.dispute_acknowledged_at.is_(None)))
        acknowledged = await db.scalar(base.where(Container.dispute_acknowledged_at.is_not(None)))
        return DisputeSummary(
            unacknowledged_count=unacknowledged or 0,
            acknowledged_count=acknowledged or 0,
        )

    @staticmethod
    async def summary(db: AsyncSession) -> MoneyRiskOut:
        """Build the combined money-risk payload powering the dashboard."""
        ar_aging = await ARagingService.summary(db)
        demurrage = await DemurrageService.countdown(db)
        disputes = await MoneyRiskService._disputes(db)
        return MoneyRiskOut(ar_aging=ar_aging, demurrage=demurrage, disputes=disputes)
