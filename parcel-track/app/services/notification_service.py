"""
NotificationService handles two concerns:
1. Writing a Notification row to the DB (in-app notification centre)
2. Dispatching an Expo push notification if the user has a push token

Called from service layer on state transitions — never from route handlers directly.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import NotificationType, UserRole
from app.db.models import Notification, ShipmentUser, User

logger = logging.getLogger("parceltrack.notifications")


# ── Notification templates ─────────────────────────────────────────────────────

NOTIFICATION_TEMPLATES: dict[NotificationType, tuple[str, str]] = {
    NotificationType.PO_SUBMITTED: (
        "PO submitted",
        "A purchase order has been submitted. Please issue an invoice.",
    ),
    NotificationType.INVOICE_RECEIVED: (
        "Invoice received",
        "A new invoice has been uploaded for your shipment.",
    ),
    NotificationType.PAYMENT_CONFIRMED: (
        "Payment confirmed",
        "Payment has been confirmed. Morocco agent can now proceed.",
    ),
    NotificationType.BL_UPLOADED: (
        "Bill of lading uploaded",
        "The BL has been uploaded and containers have been created.",
    ),
    NotificationType.VESSEL_DEPARTED: (
        "Vessel departed",
        "Your shipment has departed from the port of loading.",
    ),
    NotificationType.VESSEL_APPROACHING: (
        "Vessel approaching",
        "Your shipment is approaching the destination port.",
    ),
    NotificationType.VESSEL_DELAYED: (
        "Vessel delayed",
        "The vessel has been delayed. ETA has been revised.",
    ),
    NotificationType.VESSEL_ARRIVED: (
        "Vessel arrived",
        "The vessel has arrived at the destination port.",
    ),
    NotificationType.CONTAINER_HOLD: (
        "Container on hold",
        "A container has been placed on customs hold.",
    ),
    NotificationType.CONTAINER_CLEARED: ("Container cleared", "A container has cleared customs."),
    NotificationType.CLEARING_DOCS_URGENT: (
        "Clearing docs urgent",
        "Vessel ETA is within 48 hours — clearing docs needed urgently.",
    ),
    NotificationType.DELIVERY_SCHEDULED: (
        "Delivery scheduled",
        "Your delivery has been scheduled.",
    ),
    NotificationType.DELIVERY_COMPLETE: ("Delivery complete", "Your delivery has been completed."),
}


class NotificationService:
    @staticmethod
    async def notify_shipment_roles(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        notification_type: NotificationType,
        roles: list[UserRole],
        override_message: str | None = None,
    ) -> None:
        """Notify all members of a shipment who hold one of the given roles."""
        result = await db.execute(
            select(ShipmentUser)
            .where(ShipmentUser.shipment_id == shipment_id)
            .options(selectinload(ShipmentUser.user))
        )
        memberships = result.scalars().all()

        for membership in memberships:
            if membership.effective_role in roles:
                await NotificationService.send(
                    db=db,
                    user_id=membership.user_id,
                    shipment_id=shipment_id,
                    notification_type=notification_type,
                    override_message=override_message,
                )

    @staticmethod
    async def send(
        db: AsyncSession,
        user_id: uuid.UUID,
        shipment_id: uuid.UUID | None,
        notification_type: NotificationType,
        override_message: str | None = None,
    ) -> None:
        title, default_message = NOTIFICATION_TEMPLATES.get(
            notification_type, ("Notification", "You have a new update.")
        )
        message = override_message or default_message

        notif = Notification(
            user_id=user_id,
            shipment_id=shipment_id,
            type=notification_type,
            title=title,
            message=message,
        )
        db.add(notif)
        await db.flush()

        # Dispatch push out-of-band via Celery so the request path never waits
        # on Expo. We only enqueue when the user actually has a token to avoid
        # spawning a no-op task. The task takes the notification id (not the
        # raw token) so that a token refresh between enqueue and dispatch is
        # picked up. The caller is responsible for committing — the worker
        # only polls after the request returns, so it will see the row.
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user and user.expo_push_token:
            from app.background.tasks import send_push_notification

            send_push_notification.delay(str(notif.id))
