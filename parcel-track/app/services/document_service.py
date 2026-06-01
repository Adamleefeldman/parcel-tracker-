"""Document listing + booking-scoped authorization.

Documents are a polymorphic file store keyed by ``(entity_type, entity_id)``.
Unlike every other resource they are *not* mounted under ``/bookings/{id}/...``,
so the route layer cannot lean on ``require_booking_member`` directly. This
service resolves a document's parent entity back to its owning booking(s) and
enforces the same admin-bypass / booking-membership rule used everywhere else.

Resolution is per-entity-type because each type reaches its booking differently
(see ``resolve_booking_ids_for_document_entity``). A purchase order is M:N with
bookings via the ``booking_purchase_orders`` junction, so resolution returns a
*list* of candidate booking ids; access is granted if the actor is a member of
any of them.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentEntityType, UserRole
from app.db.models import (
    BillOfLading,
    BookingPurchaseOrder,
    BookingUser,
    ClearingDocs,
    Container,
    CustomerPayment,
    DeliveryPoint,
    DeliverySchedule,
    Document,
    Invoice,
    SupplierPayment,
    User,
)
from app.schemas.pagination import PaginationParams, paginate


class DocumentService:
    @staticmethod
    async def _booking_ids_for_po(db: AsyncSession, po_id: uuid.UUID) -> list[uuid.UUID]:
        result = await db.execute(
            select(BookingPurchaseOrder.booking_id).where(
                BookingPurchaseOrder.purchase_order_id == po_id
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def resolve_booking_ids_for_document_entity(
        db: AsyncSession,
        entity_type: DocumentEntityType | str,
        entity_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """Resolve a document's parent entity to its owning booking id(s).

        Raises 404 if the entity does not exist. Returns a (possibly empty)
        list — empty means the entity exists but is not yet attached to any
        booking (e.g. a standalone PO), which only an admin can reach.
        """
        try:
            et = (
                entity_type
                if isinstance(entity_type, DocumentEntityType)
                else DocumentEntityType(entity_type)
            )
        except ValueError as exc:
            # An unknown entity_type can never name a real entity.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown document entity type") from exc

        if et == DocumentEntityType.PURCHASE_ORDER:
            from app.db.models import PurchaseOrder

            exists = await db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.id == entity_id))
            if exists is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase order not found")
            return await DocumentService._booking_ids_for_po(db, entity_id)

        if et == DocumentEntityType.INVOICE:
            po_id = await db.scalar(
                select(Invoice.purchase_order_id).where(Invoice.id == entity_id)
            )
            if po_id is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            return await DocumentService._booking_ids_for_po(db, po_id)

        if et == DocumentEntityType.BILL_OF_LADING:
            booking_id = await db.scalar(
                select(BillOfLading.booking_id).where(BillOfLading.id == entity_id)
            )
            if booking_id is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill of lading not found")
            return [booking_id]

        if et == DocumentEntityType.CLEARING_DOCS:
            booking_id = await db.scalar(
                select(ClearingDocs.booking_id).where(ClearingDocs.id == entity_id)
            )
            if booking_id is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Clearing docs not found")
            return [booking_id]

        if et == DocumentEntityType.DELIVERY_SCHEDULE:
            booking_id = await db.scalar(
                select(DeliveryPoint.booking_id)
                .join(DeliverySchedule, DeliverySchedule.delivery_point_id == DeliveryPoint.id)
                .where(DeliverySchedule.id == entity_id)
            )
            if booking_id is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery schedule not found")
            return [booking_id]

        if et == DocumentEntityType.PAYMENT:
            # A payment document can hang off either a supplier payment
            # (outbound, via invoice → PO → booking) or a customer payment
            # (inbound, via container → BL → booking). Try supplier first.
            po_id = await db.scalar(
                select(Invoice.purchase_order_id)
                .join(SupplierPayment, SupplierPayment.invoice_id == Invoice.id)
                .where(SupplierPayment.id == entity_id)
            )
            if po_id is not None:
                return await DocumentService._booking_ids_for_po(db, po_id)

            booking_id = await db.scalar(
                select(BillOfLading.booking_id)
                .join(Container, Container.bl_id == BillOfLading.id)
                .join(CustomerPayment, CustomerPayment.container_id == Container.id)
                .where(CustomerPayment.id == entity_id)
            )
            if booking_id is not None:
                return [booking_id]

            raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")

        # Unreachable: every DocumentEntityType member is handled above.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown document entity type")

    @staticmethod
    async def assert_document_access(
        db: AsyncSession,
        entity_type: DocumentEntityType | str,
        entity_id: uuid.UUID,
        actor: User,
    ) -> None:
        """Enforce booking-scoped access for a document's parent entity.

        Mirrors ``require_booking_member``: admins always pass; everyone else
        must be a ``BookingUser`` of at least one booking the entity belongs to.
        Raises 404 if the entity does not exist, 403 if the actor has no access.
        """
        booking_ids = await DocumentService.resolve_booking_ids_for_document_entity(
            db, entity_type, entity_id
        )
        if actor.role == UserRole.ADMIN:
            return

        if booking_ids:
            membership = await db.scalar(
                select(BookingUser.id)
                .where(
                    BookingUser.booking_id.in_(booking_ids),
                    BookingUser.user_id == actor.id,
                )
                .limit(1)
            )
            if membership is not None:
                return

        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this document")

    @staticmethod
    async def list_for_entity(
        db: AsyncSession,
        entity_type: DocumentEntityType | str,
        entity_id: uuid.UUID,
        pagination: PaginationParams,
    ) -> dict:
        """Paginated documents for an entity, newest first."""
        et = (
            entity_type
            if isinstance(entity_type, DocumentEntityType)
            else DocumentEntityType(entity_type)
        )
        query = (
            select(Document)
            .where(Document.entity_type == et, Document.entity_id == entity_id)
            .order_by(Document.uploaded_at.desc())
        )
        return await paginate(db, query, pagination)
