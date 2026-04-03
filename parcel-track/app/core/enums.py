from enum import Enum


# ── Users & Roles ─────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    ADMIN = "admin"
    MOROCCO_AGENT = "morocco_agent"
    UK_AGENT = "uk_agent"
    CUSTOMER = "customer"


# ── Shipment ──────────────────────────────────────────────────────────────────

class ShipmentStatus(str, Enum):
    DRAFT = "draft"
    PO_SUBMITTED = "po_submitted"
    INVOICE_RECEIVED = "invoice_received"
    PAYMENT_CONFIRMED = "payment_confirmed"
    BL_ISSUED = "bl_issued"
    IN_TRANSIT = "in_transit"
    CLEARED = "cleared"
    COMPLETE = "complete"


# ── Purchase Order ─────────────────────────────────────────────────────────────

class POStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    LOCKED = "locked"


# ── Invoice ───────────────────────────────────────────────────────────────────

class InvoiceStatus(str, Enum):
    PENDING = "pending"
    RECEIVED = "received"
    RECONCILED = "reconciled"
    DISCREPANCY = "discrepancy"


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentType(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    DEPOSIT = "deposit"


class PaymentStatus(str, Enum):
    UPLOADED = "uploaded"
    CONFIRMED = "confirmed"


# ── Bill of Lading ─────────────────────────────────────────────────────────────

class BLStatus(str, Enum):
    UPLOADED = "uploaded"
    CONTAINERS_CREATED = "containers_created"
    LOCKED = "locked"


# ── Vessel ────────────────────────────────────────────────────────────────────

class VesselStatus(str, Enum):
    ASSIGNED = "assigned"
    ETD_SET = "etd_set"
    DEPARTED = "departed"


class VesselUpdateStatus(str, Enum):
    IN_TRANSIT = "in_transit"
    AT_WAYPOINT = "at_waypoint"
    APPROACHING = "approaching"
    ARRIVED = "arrived"
    DELAYED = "delayed"


# ── Container ─────────────────────────────────────────────────────────────────

class ContainerStatus(str, Enum):
    CREATED = "created"
    VESSEL_ASSIGNED = "vessel_assigned"
    IN_TRANSIT = "in_transit"
    AWAITING_CUSTOMS = "awaiting_customs"
    ON_HOLD = "on_hold"
    CLEARED = "cleared"
    DELIVERY_SCHEDULED = "delivery_scheduled"
    DELIVERED = "delivered"


class PortStatus(str, Enum):
    NOT_ARRIVED = "not_arrived"
    AWAITING_CUSTOMS = "awaiting_customs"
    CUSTOMS_HOLD = "customs_hold"
    RELEASED = "released"


# ── Customs ───────────────────────────────────────────────────────────────────

class CustomsStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CLEARED = "cleared"
    ON_HOLD = "on_hold"
    EXAMINATION = "examination"
    HOLD_RESOLVED = "hold_resolved"


# ── Clearing Docs ─────────────────────────────────────────────────────────────

class ClearingDocsStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETE = "complete"


# ── Delivery ──────────────────────────────────────────────────────────────────

class DeliveryStatus(str, Enum):
    AWAITING_SCHEDULE = "awaiting_schedule"
    SCHEDULED = "scheduled"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    ATTEMPTED = "attempted"
    FAILED = "failed"
    RESCHEDULED = "rescheduled"


# ── Documents ─────────────────────────────────────────────────────────────────

class DocumentEntityType(str, Enum):
    PURCHASE_ORDER = "purchase_order"
    INVOICE = "invoice"
    PAYMENT = "payment"
    BILL_OF_LADING = "bill_of_lading"
    CLEARING_DOCS = "clearing_docs"
    DELIVERY_SCHEDULE = "delivery_schedule"


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationType(str, Enum):
    PO_SUBMITTED = "po_submitted"
    INVOICE_RECEIVED = "invoice_received"
    PAYMENT_CONFIRMED = "payment_confirmed"
    BL_UPLOADED = "bl_uploaded"
    VESSEL_DEPARTED = "vessel_departed"
    VESSEL_DELAYED = "vessel_delayed"
    VESSEL_ARRIVED = "vessel_arrived"
    CONTAINER_HOLD = "container_hold"
    CONTAINER_CLEARED = "container_cleared"
    CLEARING_DOCS_URGENT = "clearing_docs_urgent"
    DELIVERY_SCHEDULED = "delivery_scheduled"
    DELIVERY_COMPLETE = "delivery_complete"


# ── Currency ──────────────────────────────────────────────────────────────────

class Currency(str, Enum):
    USD = "USD"
    GBP = "GBP"
    EUR = "EUR"
    MAD = "MAD"
