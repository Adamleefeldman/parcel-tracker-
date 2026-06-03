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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ContainerLifecycleStatus
from app.db.models import BillOfLading, Container
from app.schemas.money_risk import DisputedContainerOut, DisputeSummary, MoneyRiskOut
from app.services.ar_aging_service import ARagingService
from app.services.demurrage_service import DemurrageService


class MoneyRiskService:
    @staticmethod
    async def _disputes(db: AsyncSession) -> DisputeSummary:
        """List disputed containers (with their booking, for the dashboard
        drill-in), split by whether an admin has acknowledged the dispute.
        Lifecycle stays ``DISPUTED`` either way (history is preserved);
        acknowledgement only lifts the booking-completion blocker. Joined to the
        BL for ``booking_id`` (same path the A/R-aging summary uses)."""
        rows = (
            await db.execute(
                select(Container, BillOfLading.booking_id)
                .join(BillOfLading, Container.bl_id == BillOfLading.id)
                .where(Container.lifecycle_status == ContainerLifecycleStatus.DISPUTED)
                .order_by(Container.updated_at.asc())  # oldest dispute first
            )
        ).all()
        items = [
            DisputedContainerOut(
                container_id=container.id,
                container_number=container.container_number,
                booking_id=booking_id,
                acknowledged=container.dispute_acknowledged_at is not None,
            )
            for container, booking_id in rows
        ]
        return DisputeSummary(
            unacknowledged_count=sum(1 for i in items if not i.acknowledged),
            acknowledged_count=sum(1 for i in items if i.acknowledged),
            items=items,
        )

    @staticmethod
    async def summary(db: AsyncSession) -> MoneyRiskOut:
        """Build the combined money-risk payload powering the dashboard."""
        ar_aging = await ARagingService.summary(db)
        demurrage = await DemurrageService.countdown(db)
        disputes = await MoneyRiskService._disputes(db)
        return MoneyRiskOut(ar_aging=ar_aging, demurrage=demurrage, disputes=disputes)
