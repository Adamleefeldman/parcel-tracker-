"""Shipment-leg service (P1.1 — multi-leg routes).

A ShipmentLeg records one ordered leg of a booking's shipping route. Maersk
routes commonly transship at Algeciras with a distinct vessel/voyage per leg.

This service is intentionally additive: it does not touch `Vessel`, the
VesselFinder poller, or `ContainerLifecycleService`. Container lifecycle and
AIS polling continue to run off the 1:1 `Vessel` record (the final, arriving
leg). Legs are a route-history record surfaced in the booking detail view.
"""

import json
import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Booking, ShipmentLeg, User
from app.schemas.schemas import ShipmentLegCreate, ShipmentLegUpdate


def _snapshot(leg: ShipmentLeg) -> dict:
    """JSON-serialisable snapshot of a leg for the audit log."""

    def iso(value: date | None) -> str | None:
        return value.isoformat() if value else None

    return {
        "leg_index": leg.leg_index,
        "vessel_name": leg.vessel_name,
        "imo_number": leg.imo_number,
        "voyage_number": leg.voyage_number,
        "shipping_line": leg.shipping_line,
        "port_from": leg.port_from,
        "port_to": leg.port_to,
        "etd": iso(leg.etd),
        "atd": iso(leg.atd),
        "eta": iso(leg.eta),
        "ata": iso(leg.ata),
    }


class ShipmentLegService:
    @staticmethod
    async def _get_booking(db: AsyncSession, booking_id: uuid.UUID) -> Booking:
        result = await db.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        return booking

    @staticmethod
    async def add(
        db: AsyncSession,
        booking_id: uuid.UUID,
        body: ShipmentLegCreate,
        actor: User,
        client_ip: str | None,
    ) -> ShipmentLeg:
        """Append a leg to a booking. When `leg_index` is omitted it is set to
        the next index after the current maximum (1 for the first leg)."""
        await ShipmentLegService._get_booking(db, booking_id)

        if body.leg_index is not None:
            leg_index = body.leg_index
        else:
            max_q = await db.execute(
                select(func.max(ShipmentLeg.leg_index)).where(ShipmentLeg.booking_id == booking_id)
            )
            leg_index = (max_q.scalar() or 0) + 1

        leg = ShipmentLeg(
            booking_id=booking_id,
            leg_index=leg_index,
            vessel_name=body.vessel_name,
            imo_number=body.imo_number,
            voyage_number=body.voyage_number,
            shipping_line=body.shipping_line,
            port_from=body.port_from,
            port_to=body.port_to,
            etd=body.etd,
            eta=body.eta,
        )
        db.add(leg)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Leg index {leg_index} already exists for this booking",
            ) from None

        db.add(
            AuditLog(
                booking_id=booking_id,
                actor_id=actor.id,
                action="shipment_leg.created",
                entity_type="shipment_leg",
                entity_id=leg.id,
                old_value=None,
                new_value=json.dumps(_snapshot(leg)),
                ip_address=client_ip,
            )
        )
        return leg

    @staticmethod
    async def update(
        db: AsyncSession,
        booking_id: uuid.UUID,
        leg_id: uuid.UUID,
        body: ShipmentLegUpdate,
        actor: User,
        client_ip: str | None,
    ) -> ShipmentLeg:
        """Partial update — typically used to set atd/ata or revise eta."""
        result = await db.execute(
            select(ShipmentLeg).where(
                ShipmentLeg.id == leg_id,
                ShipmentLeg.booking_id == booking_id,
            )
        )
        leg = result.scalar_one_or_none()
        if not leg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Shipment leg not found"
            )

        old_snapshot = _snapshot(leg)
        for key, value in body.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(leg, key, value)
        await db.flush()
        # The UPDATE expires the server-side `onupdate` column (updated_at);
        # refresh so response serialisation doesn't trigger a lazy load in
        # async context (MissingGreenlet). Mirrors BookingService.update().
        await db.refresh(leg)

        db.add(
            AuditLog(
                booking_id=booking_id,
                actor_id=actor.id,
                action="shipment_leg.updated",
                entity_type="shipment_leg",
                entity_id=leg.id,
                old_value=json.dumps(old_snapshot),
                new_value=json.dumps(_snapshot(leg)),
                ip_address=client_ip,
            )
        )
        return leg

    @staticmethod
    async def list_for_booking(db: AsyncSession, booking_id: uuid.UUID) -> list[ShipmentLeg]:
        """Return every leg of a booking, ordered by leg_index."""
        await ShipmentLegService._get_booking(db, booking_id)
        result = await db.execute(
            select(ShipmentLeg)
            .where(ShipmentLeg.booking_id == booking_id)
            .order_by(ShipmentLeg.leg_index)
        )
        return list(result.scalars().all())
