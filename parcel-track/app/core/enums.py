from enum import Enum

# ── Users & Roles ─────────────────────────────────────────────────────────────


class UserRole(str, Enum):  # noqa: UP042
    ADMIN = "admin"
    MOROCCO_AGENT = "morocco_agent"
    UK_AGENT = "uk_agent"
    CUSTOMER = "customer"


# ── Booking ───────────────────────────────────────────────────────────────────
#
# A Booking is the operational unit of work: the shipping line's commercial
# commitment to move N containers from origin to destination. One Booking can
# aggregate the inventory from multiple Purchase Orders (e.g. Maersk booking
# 265232434 covers PO-2026-01; DP World booking 2601007 covers PO-2026-07 and
# PO-2026-08). One Booking maps to exactly one Bill of Lading once issued.
#
# P0.1 keeps the existing lifecycle state set under the renamed enum. P0.4 will
# replace these values with the physical-journey state set (GATE_IN, AT_SEA,
# ARRIVED, IMPORT_CLEARED, GATED_OUT, …) and add ContainerLifecycleStatus.


class BookingStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PO_SUBMITTED = "po_submitted"
    INVOICE_RECEIVED = "invoice_received"
    PAYMENT_CONFIRMED = "payment_confirmed"
    BL_ISSUED = "bl_issued"
    IN_TRANSIT = "in_transit"
    CLEARED = "cleared"
    COMPLETE = "complete"


# ── Purchase Order ─────────────────────────────────────────────────────────────


class POStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    SUBMITTED = "submitted"
    LOCKED = "locked"


# ── Invoice ───────────────────────────────────────────────────────────────────


class InvoiceStatus(str, Enum):  # noqa: UP042
    PENDING = "pending"
    RECEIVED = "received"
    RECONCILED = "reconciled"
    DISCREPANCY = "discrepancy"


# ── Payment ───────────────────────────────────────────────────────────────────
#
# Payments are bidirectional in this business:
#   * Supplier payment — outbound (USD to SCDB) against an Invoice.
#     FULL / PARTIAL / DEPOSIT capture how the wire covers the invoice value.
#   * Customer payment — inbound (GBP from broker) against a Container, with
#     cash/transfer split, variance (over/short), courier + bank-charge
#     expenses, and multi-tranche support (one container can receive several
#     deposits across days). Tracked by CustomerPaymentMethod.


class SupplierPaymentType(str, Enum):  # noqa: UP042
    FULL = "full"
    PARTIAL = "partial"
    DEPOSIT = "deposit"


class PaymentStatus(str, Enum):  # noqa: UP042
    UPLOADED = "uploaded"
    CONFIRMED = "confirmed"


class CustomerPaymentMethod(str, Enum):  # noqa: UP042
    """How an inbound customer payment was received.

    CASH    — physical handover; commonly attracts a courier fee for the
              pickup and a counting/banking charge when deposited.
    TRANSFER — bank-to-bank wire; usually attracts a bank charge.
    """

    CASH = "cash"
    TRANSFER = "transfer"


# ── Bill of Lading ─────────────────────────────────────────────────────────────


class BLStatus(str, Enum):  # noqa: UP042
    UPLOADED = "uploaded"
    CONTAINERS_CREATED = "containers_created"
    LOCKED = "locked"


# ── Vessel ────────────────────────────────────────────────────────────────────


class VesselStatus(str, Enum):  # noqa: UP042
    ASSIGNED = "assigned"
    ETD_SET = "etd_set"
    DEPARTED = "departed"


class VesselUpdateStatus(str, Enum):  # noqa: UP042
    IN_TRANSIT = "in_transit"
    AT_WAYPOINT = "at_waypoint"  # reserved for manual waypoint updates; not produced by AIS poller
    APPROACHING = "approaching"
    ARRIVED = "arrived"
    DELAYED = "delayed"


# ── Container ─────────────────────────────────────────────────────────────────


class ContainerStatus(str, Enum):  # noqa: UP042
    """Operational state of an individual container (input layer).

    These are emitted by concrete events: BL upload, vessel departure,
    customs clearance, delivery. The richer end-to-end picture (which
    includes invoicing and customer payment) lives on
    ContainerLifecycleStatus, derived from these inputs + the financial
    state.
    """

    CREATED = "created"
    VESSEL_ASSIGNED = "vessel_assigned"
    IN_TRANSIT = "in_transit"
    AWAITING_CUSTOMS = "awaiting_customs"
    ON_HOLD = "on_hold"
    CLEARED = "cleared"
    DELIVERY_SCHEDULED = "delivery_scheduled"
    DELIVERED = "delivered"


class ContainerLifecycleStatus(str, Enum):  # noqa: UP042
    """End-to-end lifecycle state of a container, derived from concrete
    events. This is what dashboards and external API consumers read.

    Driven by `ContainerLifecycleService.recompute_container_status`:
      ORDERED            — container row exists; no BL / sea events yet
      AT_SEA             — container's vessel has ATD set
      ARRIVED            — container's vessel has ATA set
      IMPORT_CLEARED     — customs cleared at destination
      DELIVERED          — last-mile delivery acknowledged
      INVOICED           — customer-facing invoice ref attached to a tranche
      PAID               — at least one tranche received but not yet banked
      BANKED             — banked_total covers the agreed sale_price_total
      CLOSED             — terminal; all reconciled
      DISPUTED           — side state, blocks the parent booking from
                           COMPLETE until acknowledged
    """

    ORDERED = "ordered"
    AT_SEA = "at_sea"
    ARRIVED = "arrived"
    IMPORT_CLEARED = "import_cleared"
    DELIVERED = "delivered"
    INVOICED = "invoiced"
    PAID = "paid"
    BANKED = "banked"
    CLOSED = "closed"
    DISPUTED = "disputed"


class PortStatus(str, Enum):  # noqa: UP042
    NOT_ARRIVED = "not_arrived"
    AWAITING_CUSTOMS = "awaiting_customs"
    CUSTOMS_HOLD = "customs_hold"
    RELEASED = "released"


# ── Customs ───────────────────────────────────────────────────────────────────


class CustomsStatus(str, Enum):  # noqa: UP042
    PENDING = "pending"
    SUBMITTED = "submitted"
    CLEARED = "cleared"
    ON_HOLD = "on_hold"
    EXAMINATION = "examination"
    HOLD_RESOLVED = "hold_resolved"


# ── Clearing Docs ─────────────────────────────────────────────────────────────


class ClearingDocsStatus(str, Enum):  # noqa: UP042
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETE = "complete"


# ── Delivery ──────────────────────────────────────────────────────────────────


class DeliveryStatus(str, Enum):  # noqa: UP042
    AWAITING_SCHEDULE = "awaiting_schedule"
    SCHEDULED = "scheduled"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    ATTEMPTED = "attempted"
    FAILED = "failed"
    RESCHEDULED = "rescheduled"


class DeliveryType(str, Enum):  # noqa: UP042
    """How a container moves from the UK port to its end customer.

    DIRECT      — port → customer (single haulage leg, typical when one
                  buyer takes the whole 21-pallet container)
    VIA_WAREHOUSE — port → warehouse → customer(s) (split shipments, pallet
                    rebundling, or mixed-SKU containers reorganised before
                    the last-mile drop)
    """

    DIRECT = "direct"
    VIA_WAREHOUSE = "via_warehouse"


# ── Documents ─────────────────────────────────────────────────────────────────


class DocumentEntityType(str, Enum):  # noqa: UP042
    PURCHASE_ORDER = "purchase_order"
    INVOICE = "invoice"
    PAYMENT = "payment"
    BILL_OF_LADING = "bill_of_lading"
    CLEARING_DOCS = "clearing_docs"
    DELIVERY_SCHEDULE = "delivery_schedule"


# ── Notifications ─────────────────────────────────────────────────────────────


class NotificationType(str, Enum):  # noqa: UP042
    PO_SUBMITTED = "po_submitted"
    INVOICE_RECEIVED = "invoice_received"
    PAYMENT_CONFIRMED = "payment_confirmed"
    BL_UPLOADED = "bl_uploaded"
    VESSEL_DEPARTED = "vessel_departed"
    VESSEL_APPROACHING = "vessel_approaching"
    VESSEL_DELAYED = "vessel_delayed"
    VESSEL_ARRIVED = "vessel_arrived"
    CONTAINER_HOLD = "container_hold"
    CONTAINER_CLEARED = "container_cleared"
    CLEARING_DOCS_URGENT = "clearing_docs_urgent"
    DELIVERY_SCHEDULED = "delivery_scheduled"
    DELIVERY_COMPLETE = "delivery_complete"
    AR_AGING_ALERT = "ar_aging_alert"
    DEMURRAGE_WARNING = "demurrage_warning"


# ── UK ports (P1.3) ───────────────────────────────────────────────────────────
#
# UK port of discharge. Each port has distinct free-day defaults and fee
# structures, captured per-port in the PortTemplate table. OTHER is the
# catch-all for ports not yet modelled.


class UKPort(str, Enum):  # noqa: UP042
    FELIXSTOWE = "felixstowe"
    LONDON_GATEWAY = "london_gateway"
    TILBURY = "tilbury"
    SOUTHAMPTON = "southampton"
    LIVERPOOL = "liverpool"
    OTHER = "other"


# ── Currency ──────────────────────────────────────────────────────────────────


class Currency(str, Enum):  # noqa: UP042
    USD = "USD"
    GBP = "GBP"
    EUR = "EUR"
    MAD = "MAD"
