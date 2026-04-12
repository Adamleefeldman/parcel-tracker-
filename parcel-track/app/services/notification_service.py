"""
NotificationService handles two concerns:
1. Writing a Notification row to the DB (in-app notification centre)
2. Dispatching an Expo push notification if the user has a push token

Called from service layer on state transitions — never from route handlers directly.
"""

import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.enums import NotificationType, UserRole
from app.db.models import Notification, ShipmentUser, User

settings = get_settings()


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

        # Dispatch push if user has a token
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user and user.expo_push_token:
            await NotificationService._send_push(user.expo_push_token, title, message)
            notif.push_sent = True

    @staticmethod
    async def _send_push(token: str, title: str, body: str) -> None:
        payload = {
            "to": token,
            "title": title,
            "body": body,
            "sound": "default",
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(settings.EXPO_PUSH_URL, json=payload)
        except Exception:  # noqa: S110
            pass  # Push failure is non-fatal — notification is already in DB
