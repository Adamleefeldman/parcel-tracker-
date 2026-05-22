"""Port-template service (P1.3).

A PortTemplate carries the default detention/demurrage free-days and
post-free-time rates for a UK discharge port. When a BL is created with a
`port_of_discharge`, the parent Booking inherits these defaults for any P1.2
booking-confirmation fields not already populated.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UKPort
from app.db.models import Booking, PortTemplate
from app.schemas.schemas import PortTemplateUpsert


class PortTemplateService:
    @staticmethod
    async def list_all(db: AsyncSession) -> list[PortTemplate]:
        result = await db.execute(select(PortTemplate).order_by(PortTemplate.port))
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, port: UKPort) -> PortTemplate | None:
        result = await db.execute(select(PortTemplate).where(PortTemplate.port == port))
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(db: AsyncSession, port: UKPort, body: PortTemplateUpsert) -> PortTemplate:
        """Create or update the template for a port (one row per UKPort)."""
        template = await PortTemplateService.get(db, port)
        if template is None:
            template = PortTemplate(port=port)
            db.add(template)
        template.free_days_detention = body.free_days_detention
        template.free_days_demurrage = body.free_days_demurrage
        template.detention_rate_gbp_after = body.detention_rate_gbp_after
        template.demurrage_rate_gbp_after = body.demurrage_rate_gbp_after
        await db.flush()
        await db.refresh(template)
        return template

    @staticmethod
    async def apply_to_booking(db: AsyncSession, booking_id: uuid.UUID, port: UKPort) -> None:
        """Fill any unset P1.2 free-day / rate fields on a booking from the
        port's template. Existing (non-NULL) values are never overwritten."""
        template = await PortTemplateService.get(db, port)
        if template is None:
            return
        booking_result = await db.execute(select(Booking).where(Booking.id == booking_id))
        booking = booking_result.scalar_one_or_none()
        if booking is None:
            return
        if booking.free_days_detention is None:
            booking.free_days_detention = template.free_days_detention
        if booking.free_days_demurrage is None:
            booking.free_days_demurrage = template.free_days_demurrage
        if booking.detention_rate_gbp_after is None:
            booking.detention_rate_gbp_after = template.detention_rate_gbp_after
        if booking.demurrage_rate_gbp_after is None:
            booking.demurrage_rate_gbp_after = template.demurrage_rate_gbp_after
        await db.flush()
