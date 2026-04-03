"""
ShipmentService owns all state machine logic.
No route handler or other service should write shipment.status directly —
all transitions flow through transition_status() which enforces preconditions.
"""
from unittest import result
import uuid
import json
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.enums import (
    ShipmentStatus, POStatus, InvoiceStatus, PaymentStatus,
    BLStatus, VesselStatus, ContainerStatus, CustomsStatus,
    DeliveryStatus, UserRole,
)
from app.db.models import (
    Shipment, ShipmentUser, PurchaseOrder, Invoice, Payment,
    BillOfLading, Container, Vessel, ClearingDocs, CustomsRecord,
    DeliveryPoint, DeliveryContainer, AuditLog, User,
)
from app.schemas import schemas


# ── Allowed state transitions ─────────────────────────────────────────────────

VALID_TRANSITIONS: dict[ShipmentStatus, list[ShipmentStatus]] = {
    ShipmentStatus.DRAFT:              [ShipmentStatus.PO_SUBMITTED],
    ShipmentStatus.PO_SUBMITTED:       [ShipmentStatus.INVOICE_RECEIVED],
    ShipmentStatus.INVOICE_RECEIVED:   [ShipmentStatus.PAYMENT_CONFIRMED],
    ShipmentStatus.PAYMENT_CONFIRMED:  [ShipmentStatus.BL_ISSUED],
    ShipmentStatus.BL_ISSUED:          [ShipmentStatus.IN_TRANSIT],
    ShipmentStatus.IN_TRANSIT:         [ShipmentStatus.CLEARED],
    ShipmentStatus.CLEARED:            [ShipmentStatus.COMPLETE],
    ShipmentStatus.COMPLETE:           [],  # terminal
}


class ShipmentService:

    @staticmethod
    async def create(db: AsyncSession, reference: str, actor: User) -> Shipment:
        # Ensure unique reference
        exists = await db.execute(select(Shipment).where(Shipment.reference == reference))
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Shipment reference '{reference}' already exists")

        shipment = Shipment(reference=reference, created_by=actor.id)
        db.add(shipment)
        await db.flush()

        # Admin is automatically a member
        db.add(ShipmentUser(shipment_id=shipment.id, user_id=actor.id))
        await db.flush()

        return shipment

    @staticmethod
    async def get(db: AsyncSession, shipment_id: uuid.UUID, actor: User) -> Shipment:
        result = await db.execute(
            select(Shipment)
            .where(Shipment.id == shipment_id)
            .options(
                selectinload(Shipment.purchase_order),
                selectinload(Shipment.invoice),
                selectinload(Shipment.payments),
                selectinload(Shipment.bill_of_lading).selectinload(BillOfLading.containers),
                selectinload(Shipment.bill_of_lading).selectinload(BillOfLading.vessel).selectinload(Vessel.updates),
                selectinload(Shipment.clearing_docs),
                selectinload(Shipment.delivery_points).selectinload(DeliveryPoint.schedule),
                selectinload(Shipment.delivery_points).selectinload(DeliveryPoint.container_assignments).selectinload(DeliveryContainer.container),
            )
        )
        shipment = result.scalar_one_or_none()
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")
        return shipment
    
    @staticmethod
    async def update(db: AsyncSession, shipment_id: uuid.UUID, data: dict, actor: User) -> Shipment:
        result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
        shipment = result.scalar_one_or_none()
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")

        for key, value in data.items():
            if value is not None:
                setattr(shipment, key, value)

        await db.flush()
        await db.refresh(shipment)
        return shipment

    @staticmethod
    async def transition_status(
        db: AsyncSession,
        shipment: Shipment,
        new_status: ShipmentStatus,
        actor: User,
        ip: Optional[str] = None,
    ) -> Shipment:
        """
        Central state gate. Checks:
        1. Transition is in VALID_TRANSITIONS
        2. All preconditions for the target state are met
        Then writes the new status and logs the change.
        """
        current = shipment.status
        if new_status not in VALID_TRANSITIONS.get(current, []):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{current}' to '{new_status}'"
            )

        await ShipmentService._check_preconditions(db, shipment, new_status)

        old_status = shipment.status
        shipment.status = new_status

        db.add(AuditLog(
            shipment_id=shipment.id,
            actor_id=actor.id,
            action="shipment.status_changed",
            entity_type="shipment",
            entity_id=shipment.id,
            old_value=json.dumps({"status": old_status.value}),
            new_value=json.dumps({"status": new_status.value}),
            ip_address=ip,
        ))

        return shipment

    @staticmethod
    async def _check_preconditions(
        db: AsyncSession,
        shipment: Shipment,
        target: ShipmentStatus,
    ) -> None:
        """Raises HTTPException if preconditions for target state are not met."""

        if target == ShipmentStatus.PO_SUBMITTED:
            po = await db.execute(select(PurchaseOrder).where(
                PurchaseOrder.shipment_id == shipment.id,
                PurchaseOrder.status == POStatus.SUBMITTED,
            ))
            if not po.scalar_one_or_none():
                raise HTTPException(400, "PO must be submitted with document before proceeding")

        elif target == ShipmentStatus.INVOICE_RECEIVED:
            inv = await db.execute(select(Invoice).where(Invoice.shipment_id == shipment.id))
            invoice = inv.scalar_one_or_none()
            if not invoice or invoice.status not in (InvoiceStatus.RECEIVED, InvoiceStatus.RECONCILED):
                raise HTTPException(400, "Invoice must be uploaded before proceeding")
            if invoice.status == InvoiceStatus.DISCREPANCY and not invoice.discrepancy_acknowledged:
                raise HTTPException(400, "Invoice discrepancy must be acknowledged before proceeding")

        elif target == ShipmentStatus.PAYMENT_CONFIRMED:
            # Cumulative payments must equal or exceed invoice value
            inv = await db.execute(select(Invoice).where(Invoice.shipment_id == shipment.id))
            invoice = inv.scalar_one_or_none()
            if not invoice:
                raise HTTPException(400, "No invoice found")

            total_paid = await db.execute(
                select(func.sum(Payment.amount)).where(
                    Payment.shipment_id == shipment.id,
                    Payment.status == PaymentStatus.CONFIRMED,
                )
            )
            paid = total_paid.scalar() or Decimal("0")
            if paid < invoice.value:
                raise HTTPException(400, f"Payments ({paid}) do not cover invoice value ({invoice.value})")

        elif target == ShipmentStatus.BL_ISSUED:
            bl = await db.execute(select(BillOfLading).where(BillOfLading.shipment_id == shipment.id))
            if not bl.scalar_one_or_none():
                raise HTTPException(400, "Bill of lading must be uploaded before proceeding")

        elif target == ShipmentStatus.IN_TRANSIT:
            vessel = await db.execute(
                select(Vessel)
                .join(BillOfLading, Vessel.bl_id == BillOfLading.id)
                .where(BillOfLading.shipment_id == shipment.id)
            )
            v = vessel.scalar_one_or_none()
            if not v or not v.atd:
                raise HTTPException(400, "Vessel actual departure date (ATD) must be confirmed")

        elif target == ShipmentStatus.CLEARED:
            # All containers must be cleared
            containers = await db.execute(
                select(Container)
                .join(BillOfLading, Container.bl_id == BillOfLading.id)
                .where(BillOfLading.shipment_id == shipment.id)
            )
            all_containers = containers.scalars().all()
            if not all_containers:
                raise HTTPException(400, "No containers found for this shipment")
            not_cleared = [c for c in all_containers if c.status != ContainerStatus.CLEARED]
            if not_cleared:
                raise HTTPException(400, f"{len(not_cleared)} container(s) not yet cleared through customs")

        elif target == ShipmentStatus.COMPLETE:
            # All delivery points must be delivered
            points = await db.execute(
                select(DeliveryPoint).where(DeliveryPoint.shipment_id == shipment.id)
            )
            all_points = points.scalars().all()
            if not all_points:
                raise HTTPException(400, "No delivery points found for this shipment")
            not_delivered = [p for p in all_points if p.status != DeliveryStatus.DELIVERED]
            if not_delivered:
                raise HTTPException(400, f"{len(not_delivered)} delivery point(s) not yet delivered")

    @staticmethod
    def mask_financials(obj: dict, show: bool) -> dict:
        """Strip financial keys from a dict when show=False (non-admin)."""
        if show:
            return obj
        financial_keys = {"total_value", "value", "amount", "swift_ref", "duty_paid", "estimated_duty_vat"}
        return {k: (None if k in financial_keys else v) for k, v in obj.items()}
