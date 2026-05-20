"""
Database models — all tables in one file for clarity.
Relationships are explicit; cascade rules are intentional.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.enums import (
    BLStatus,
    BookingStatus,
    ClearingDocsStatus,
    ContainerLifecycleStatus,
    ContainerStatus,
    Currency,
    CustomerPaymentMethod,
    CustomsStatus,
    DeliveryStatus,
    DeliveryType,
    DocumentEntityType,
    InvoiceStatus,
    NotificationType,
    PaymentStatus,
    PortStatus,
    POStatus,
    SupplierPaymentType,
    UserRole,
    VesselStatus,
    VesselUpdateStatus,
)
from app.db.database import Base

# ── Helpers ───────────────────────────────────────────────────────────────────


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def now_utc():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at():
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ── Users ─────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False)
    expo_push_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    # Relationships
    booking_memberships: Mapped[list["BookingUser"]] = relationship(back_populates="user")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    invite_tokens: Mapped[list["InviteToken"]] = relationship(back_populates="created_by_user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = now_utc()

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class InviteToken(Base):
    __tablename__ = "invite_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = now_utc()

    created_by_user: Mapped["User"] = relationship(back_populates="invite_tokens")


# ── Booking + membership ──────────────────────────────────────────────────────


class Booking(Base):
    """
    A Booking is the shipping-line commitment to move N containers from origin
    to destination. It aggregates one or more PurchaseOrders via the
    booking_purchase_orders junction table. One Booking maps to one BL once
    issued. The `booking_number` is the carrier reference (e.g. Maersk
    265232434, MSC MEDUCA381150) — assigned by the shipping line; nullable
    until the Booking Confirmation is received.
    """

    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = uuid_pk()
    reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    booking_number: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    status: Mapped[BookingStatus] = mapped_column(
        SAEnum(BookingStatus), default=BookingStatus.DRAFT, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    # Relationships
    members: Mapped[list["BookingUser"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )
    purchase_order_links: Mapped[list["BookingPurchaseOrder"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )
    bill_of_lading: Mapped[Optional["BillOfLading"]] = relationship(
        back_populates="booking", uselist=False
    )
    clearing_docs: Mapped[Optional["ClearingDocs"]] = relationship(
        back_populates="booking", uselist=False
    )
    delivery_points: Mapped[list["DeliveryPoint"]] = relationship(back_populates="booking")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="booking")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="booking")
    # Ordered list of transshipment legs (P1.1). A direct sailing has one leg;
    # a Maersk route via Algeciras has two (Casablanca→Algeciras, then
    # Algeciras→London Gateway), each with its own vessel + voyage.
    legs: Mapped[list["ShipmentLeg"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="ShipmentLeg.leg_index",
    )

    @property
    def purchase_orders(self) -> list["PurchaseOrder"]:
        """Convenience accessor: flatten the junction table into the PO list."""
        return [link.purchase_order for link in self.purchase_order_links]


class BookingUser(Base):
    """Junction: which users have access to which bookings, and at what role."""

    __tablename__ = "booking_users"
    __table_args__ = (UniqueConstraint("booking_id", "user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Allows role override per booking (e.g. someone acting as UK agent only for this job)
    role_override: Mapped[UserRole | None] = mapped_column(SAEnum(UserRole), nullable=True)
    added_at: Mapped[datetime] = now_utc()

    booking: Mapped["Booking"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="booking_memberships")

    @property
    def effective_role(self) -> UserRole:
        return self.role_override if self.role_override else self.user.role


class BookingPurchaseOrder(Base):
    """
    Junction: which POs are aggregated under which Booking.
    Many-to-many because one Booking can carry multiple POs (real example:
    DP World booking 2601008 covers PO-2026-04 + PO-2026-05) and a single PO
    can in principle be split across bookings if the supplier ships partial
    consignments.
    """

    __tablename__ = "booking_purchase_orders"
    __table_args__ = (UniqueConstraint("booking_id", "purchase_order_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    added_at: Mapped[datetime] = now_utc()

    booking: Mapped["Booking"] = relationship(back_populates="purchase_order_links")
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="booking_links")


# ── Customer-side parties: Broker + Company ──────────────────────────────────
#
# These are intentionally minimal in P0.2 — full customer CRM is deferred.
# A Broker is the POC who arranges and collects payment (e.g. "ZAF" for
# Zayyan Foods Distribution, "IFFY" for Iffy at Surplus Stock Deals).
# A Company is the end-buyer firm receiving the container (Chesertons,
# Surplus, Aryana, BFC, etc.). One Container has at most one Broker and
# one Company; both FKs are nullable while the deal is being arranged.


class Broker(Base):
    __tablename__ = "brokers"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()


class Company(Base):
    """End-buyer / receiving company. `aliases` carries free-form alternate
    spellings ("CHESERTON" / "CHESERTONS" / "CHESERTONS LTD") so import paths
    can deduplicate without a full CRM. Stored as JSON list-of-strings — works
    on both Postgres (jsonb behaviour) and SQLite (TEXT)."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = uuid_pk()
    legal_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    registration_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vat_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    default_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()


# ── Financial: PO, Invoice, Payment ──────────────────────────────────────────


class PurchaseOrder(Base):
    """
    Purchase Order — created by admin and sent to the supplier (SCDB).
    A PO exists independently of any Booking until it gets aggregated into one.
    One PO has at most one supplier Commercial Invoice (Invoice). One PO can
    be linked to one Booking via BookingPurchaseOrder (the junction enforces
    uniqueness within a booking but permits split-across-bookings shipments).
    """

    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_purchase_orders_quantity_non_negative"),
        CheckConstraint("total_value >= 0", name="ck_purchase_orders_total_value_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    po_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    po_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(SAEnum(Currency), nullable=False)
    status: Mapped[POStatus] = mapped_column(
        SAEnum(POStatus), default=POStatus.DRAFT, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    invoice: Mapped[Optional["Invoice"]] = relationship(
        back_populates="purchase_order", uselist=False
    )
    booking_links: Mapped[list["BookingPurchaseOrder"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )
    document: Mapped[Optional["Document"]] = relationship(
        primaryjoin=(
            "and_(Document.entity_type=='purchase_order',"
            " foreign(Document.entity_id)==PurchaseOrder.id)"
        ),
        foreign_keys="Document.entity_id",
        uselist=False,
        viewonly=True,
    )

    @property
    def bookings(self) -> list["Booking"]:
        """Convenience accessor: flatten the junction table into the booking list."""
        return [link.booking for link in self.booking_links]


class Invoice(Base):
    """
    Supplier Commercial Invoice — one per PurchaseOrder. Issued by SCDB on
    shipment. Distinct from outbound customer invoices (deferred).
    """

    __tablename__ = "invoices"
    __table_args__ = (CheckConstraint("value >= 0", name="ck_invoices_value_non_negative"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(SAEnum(Currency), nullable=False)
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus), default=InvoiceStatus.PENDING, nullable=False
    )
    discrepancy_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="invoice")
    supplier_payments: Mapped[list["SupplierPayment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class SupplierPayment(Base):
    """Outbound payment to the supplier (USD wire to SCDB) against a specific
    supplier Invoice. Multi-PO bookings have multiple Invoices (one per PO);
    each Invoice has its own SupplierPayment(s) summing to its value.
    """

    __tablename__ = "supplier_payments"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_supplier_payments_amount_positive"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    swift_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(SAEnum(Currency), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_type: Mapped[SupplierPaymentType] = mapped_column(
        SAEnum(SupplierPaymentType, name="paymenttype"), nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus), default=PaymentStatus.UPLOADED, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_utc()

    invoice: Mapped["Invoice"] = relationship(back_populates="supplier_payments")


class CustomerPayment(Base):
    """Inbound payment from a UK customer for a specific Container.

    Captures the structure from the trading-tracker spreadsheet: cash or
    transfer, optional variance (over/short of the agreed amount), courier
    and bank-charge expenses, multi-tranche support (the same container can
    accept N tranches across days), and the outbound customer invoice
    reference (`customer_invoice_ref`) that batched this payment with
    others. The full outbound CustomerInvoice entity stays deferred per the
    scope decision; we record the ref string here so reconciliation works
    today even without a dedicated invoice table.
    """

    __tablename__ = "customer_payments"
    __table_args__ = (
        CheckConstraint(
            "amount_received > 0", name="ck_customer_payments_amount_received_positive"
        ),
        CheckConstraint(
            "expense_courier IS NULL OR expense_courier >= 0",
            name="ck_customer_payments_expense_courier_non_negative",
        ),
        CheckConstraint(
            "expense_bank_charge IS NULL OR expense_bank_charge >= 0",
            name="ck_customer_payments_expense_bank_charge_non_negative",
        ),
        CheckConstraint("tranche_index >= 1", name="ck_customer_payments_tranche_index_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[CustomerPaymentMethod] = mapped_column(
        SAEnum(CustomerPaymentMethod), nullable=False
    )
    amount_received: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # variance can be negative (short) or positive (over) — Decimal not constrained.
    variance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expense_courier: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    expense_bank_charge: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    banked_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    sender_bank: Mapped[str | None] = mapped_column(String(200), nullable=True)
    receiver_bank: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tranche_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    customer_invoice_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_utc()

    container: Mapped["Container"] = relationship()


# ── Bill of Lading + Vessel ───────────────────────────────────────────────────


class BillOfLading(Base):
    __tablename__ = "bills_of_lading"
    __table_args__ = (
        CheckConstraint("container_count > 0", name="ck_bills_of_lading_container_count_positive"),
        CheckConstraint("gross_weight_kg > 0", name="ck_bills_of_lading_gross_weight_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    bl_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    bl_date: Mapped[date] = mapped_column(Date, nullable=False)
    shipper_name: Mapped[str] = mapped_column(String(255), nullable=False)
    consignee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    notify_party: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port_of_loading: Mapped[str] = mapped_column(String(100), nullable=False)
    port_of_discharge: Mapped[str] = mapped_column(String(100), nullable=False)
    container_count: Mapped[int] = mapped_column(Integer, nullable=False)
    commodity_description: Mapped[str] = mapped_column(Text, nullable=False)
    gross_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[BLStatus] = mapped_column(
        SAEnum(BLStatus), default=BLStatus.UPLOADED, nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    booking: Mapped["Booking"] = relationship(back_populates="bill_of_lading")
    containers: Mapped[list["Container"]] = relationship(
        back_populates="bill_of_lading", cascade="all, delete-orphan"
    )
    vessel: Mapped[Optional["Vessel"]] = relationship(
        back_populates="bill_of_lading", uselist=False
    )


class Vessel(Base):
    __tablename__ = "vessels"

    id: Mapped[uuid.UUID] = uuid_pk()
    bl_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bills_of_lading.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    vessel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    imo_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    voyage_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shipping_line: Mapped[str] = mapped_column(String(255), nullable=False)
    port_of_loading: Mapped[str] = mapped_column(String(100), nullable=False)
    port_of_discharge: Mapped[str] = mapped_column(String(100), nullable=False)
    etd: Mapped[date | None] = mapped_column(Date, nullable=True)
    atd: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )  # actual departure — triggers in_transit
    eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    ata: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )  # actual arrival — triggers ContainerLifecycleStatus.ARRIVED
    status: Mapped[VesselStatus] = mapped_column(
        SAEnum(VesselStatus), default=VesselStatus.ASSIGNED, nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    bill_of_lading: Mapped["BillOfLading"] = relationship(back_populates="vessel")
    updates: Mapped[list["VesselUpdate"]] = relationship(
        back_populates="vessel", order_by="VesselUpdate.created_at"
    )


class VesselUpdate(Base):
    """Append-only log — never update rows, only insert."""

    __tablename__ = "vessel_updates"

    id: Mapped[uuid.UUID] = uuid_pk()
    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vessels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable: background-task writes (e.g. VesselFinder poller) have no
    # acting user. NULL means "system-generated"; pair with `source` to
    # identify the writer. Route-layer writes always set this.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[VesselUpdateStatus] = mapped_column(SAEnum(VesselUpdateStatus), nullable=False)
    current_position_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(
        String(100), default="myshippingtracking.com", nullable=False
    )
    created_at: Mapped[datetime] = now_utc()

    vessel: Mapped["Vessel"] = relationship(back_populates="updates")


# ── Shipment legs ─────────────────────────────────────────────────────────────


class ShipmentLeg(Base):
    """
    One ordered leg of a booking's shipping route (P1.1).

    Real Maersk routes transship at Algeciras with a distinct vessel and
    voyage per leg (e.g. Casablanca→Algeciras on MAERSK NEWARK V602E, then
    Algeciras→London Gateway on MADRID MAERSK V601W). `Vessel` (1:1 with the
    BL) stays the polling + lifecycle driver for the final, UK-arriving leg;
    `ShipmentLeg` records the full ordered route for visibility. `leg_index`
    is 1-based and unique within a booking.
    """

    __tablename__ = "shipment_legs"
    __table_args__ = (
        UniqueConstraint("booking_id", "leg_index", name="uq_shipment_legs_booking_leg_index"),
        CheckConstraint("leg_index >= 1", name="ck_shipment_legs_leg_index_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    leg_index: Mapped[int] = mapped_column(Integer, nullable=False)
    vessel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    imo_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    voyage_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shipping_line: Mapped[str] = mapped_column(String(255), nullable=False)
    port_from: Mapped[str] = mapped_column(String(100), nullable=False)
    port_to: Mapped[str] = mapped_column(String(100), nullable=False)
    etd: Mapped[date | None] = mapped_column(Date, nullable=True)
    atd: Mapped[date | None] = mapped_column(Date, nullable=True)
    eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    ata: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    booking: Mapped["Booking"] = relationship(back_populates="legs")


# ── Containers ────────────────────────────────────────────────────────────────


class Container(Base):
    """A shipping container — the operational unit of the business.

    Carries both the transit-side fields (port/customs status, BL link) and
    the sale-side fields (delivery type, broker, end company, agreed sale
    prices in GBP). Per-container sale prices vary because each container
    can go to a different buyer at a different negotiated rate (e.g. £5.95
    list for Chesertons vs £6.30 premium for Surplus). Currency defaults to
    GBP since UK is the sole destination today; deferred FX work will
    generalise this.
    """

    __tablename__ = "containers"
    __table_args__ = (
        CheckConstraint(
            "sale_price_per_tray IS NULL OR sale_price_per_tray >= 0",
            name="ck_containers_sale_price_per_tray_non_negative",
        ),
        CheckConstraint(
            "sale_price_per_pallet IS NULL OR sale_price_per_pallet >= 0",
            name="ck_containers_sale_price_per_pallet_non_negative",
        ),
        CheckConstraint(
            "sale_price_total IS NULL OR sale_price_total >= 0",
            name="ck_containers_sale_price_total_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    bl_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bills_of_lading.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    container_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    seal_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    port_status: Mapped[PortStatus] = mapped_column(
        SAEnum(PortStatus), default=PortStatus.NOT_ARRIVED, nullable=False
    )
    status: Mapped[ContainerStatus] = mapped_column(
        SAEnum(ContainerStatus), default=ContainerStatus.CREATED, nullable=False
    )
    destin8_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Lifecycle (P0.4) ─────────────────────────────────────────────────
    # Derived from concrete events by ContainerLifecycleService.
    # `dispute_reason` / `disputed_at` are populated when lifecycle_status
    # is set to DISPUTED; otherwise both are NULL.
    lifecycle_status: Mapped[ContainerLifecycleStatus] = mapped_column(
        SAEnum(ContainerLifecycleStatus),
        default=ContainerLifecycleStatus.ORDERED,
        nullable=False,
    )
    dispute_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Sale-side ────────────────────────────────────────────────────────
    delivery_type: Mapped[DeliveryType | None] = mapped_column(SAEnum(DeliveryType), nullable=True)
    broker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brokers.id"), nullable=True, index=True
    )
    end_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True
    )
    sale_price_per_tray: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sale_price_per_pallet: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    sale_price_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    sale_currency: Mapped[Currency] = mapped_column(
        SAEnum(Currency), default=Currency.GBP, nullable=False
    )

    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    bill_of_lading: Mapped["BillOfLading"] = relationship(back_populates="containers")
    customs_record: Mapped[Optional["CustomsRecord"]] = relationship(
        back_populates="container", uselist=False
    )
    delivery_assignments: Mapped[list["DeliveryContainer"]] = relationship(
        back_populates="container"
    )
    # NB: Per CLAUDE.md these relationships use the default lazy strategy.
    # Callers that need broker / end_company must add explicit selectinload()
    # at query time (lazy access in async context would crash).
    broker: Mapped[Optional["Broker"]] = relationship()
    end_company: Mapped[Optional["Company"]] = relationship()


# ── Clearing Docs + Customs ───────────────────────────────────────────────────


class ClearingDocs(Base):
    __tablename__ = "clearing_docs"
    __table_args__ = (
        CheckConstraint(
            "duty_rate IS NULL OR duty_rate >= 0", name="ck_clearing_docs_duty_rate_non_negative"
        ),
        CheckConstraint(
            "estimated_duty_vat IS NULL OR estimated_duty_vat >= 0",
            name="ck_clearing_docs_estimated_duty_vat_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    customs_entry_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hs_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duty_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    estimated_duty_vat: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Checklist booleans — each ticked when the doc is uploaded
    has_customs_entry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_packing_list: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_certificate_of_origin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_health_cert: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # optional
    status: Mapped[ClearingDocsStatus] = mapped_column(
        SAEnum(ClearingDocsStatus), default=ClearingDocsStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    booking: Mapped["Booking"] = relationship(back_populates="clearing_docs")


class CustomsRecord(Base):
    __tablename__ = "customs_records"
    __table_args__ = (
        CheckConstraint(
            "duty_paid IS NULL OR duty_paid >= 0", name="ck_customs_records_duty_paid_non_negative"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    status: Mapped[CustomsStatus] = mapped_column(
        SAEnum(CustomsStatus), default=CustomsStatus.PENDING, nullable=False
    )
    clearance_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hmrc_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duty_paid: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Append-only notes stored as a JSONB-style text log; use CustomsNote for structured append
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    container: Mapped["Container"] = relationship(back_populates="customs_record")
    notes: Mapped[list["CustomsNote"]] = relationship(
        back_populates="customs_record", order_by="CustomsNote.created_at"
    )


class CustomsNote(Base):
    """Append-only log for customs hold resolution notes."""

    __tablename__ = "customs_notes"

    id: Mapped[uuid.UUID] = uuid_pk()
    customs_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customs_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = now_utc()

    customs_record: Mapped["CustomsRecord"] = relationship(back_populates="notes")


# ── Delivery ──────────────────────────────────────────────────────────────────


class DeliveryPoint(Base):
    __tablename__ = "delivery_points"

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Customer-side parties for last-mile delivery (P0.5). Both nullable
    # while the deal is being arranged; the broker is the POC arranging
    # the drop (e.g. ZAF / IFFY) and the end_company is the buying firm.
    broker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brokers.id"), nullable=True, index=True
    )
    end_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True
    )
    # Direct (port → customer) or Via Warehouse (port → W/H → customer(s)).
    # Mirrors the spreadsheet's Delivery Type column; nullable until set.
    delivery_type: Mapped[DeliveryType | None] = mapped_column(SAEnum(DeliveryType), nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rebundled_at_warehouse: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Legacy: customer_user_id used to point at a User record. With the
    # Company/Broker split it's redundant — kept nullable for back-compat
    # with old data, will be retired in a follow-up.
    customer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    special_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(DeliveryStatus), default=DeliveryStatus.AWAITING_SCHEDULE, nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    broker: Mapped[Optional["Broker"]] = relationship()
    end_company: Mapped[Optional["Company"]] = relationship()

    booking: Mapped["Booking"] = relationship(back_populates="delivery_points")
    container_assignments: Mapped[list["DeliveryContainer"]] = relationship(
        back_populates="delivery_point", cascade="all, delete-orphan"
    )
    schedule: Mapped[Optional["DeliverySchedule"]] = relationship(
        back_populates="delivery_point", uselist=False
    )

    @property
    def containers(self) -> list["Container"]:
        """Convenience accessor used by DeliveryPointOut schema — flattens the junction table."""
        return [a.container for a in self.container_assignments]


class DeliveryContainer(Base):
    """Junction: which containers go to which delivery point."""

    __tablename__ = "delivery_containers"
    __table_args__ = (UniqueConstraint("delivery_point_id", "container_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    delivery_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("delivery_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    delivery_point: Mapped["DeliveryPoint"] = relationship(back_populates="container_assignments")
    container: Mapped["Container"] = relationship(back_populates="delivery_assignments")


class DeliverySchedule(Base):
    __tablename__ = "delivery_schedules"

    id: Mapped[uuid.UUID] = uuid_pk()
    delivery_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("delivery_points.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_window_start: Mapped[str] = mapped_column(String(10), nullable=False)  # "07:00"
    time_window_end: Mapped[str] = mapped_column(String(10), nullable=False)  # "12:00"
    haulier: Mapped[str] = mapped_column(String(255), nullable=False)
    driver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vehicle_reg: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes_to_recipient: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(DeliveryStatus), default=DeliveryStatus.SCHEDULED, nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    delivery_point: Mapped["DeliveryPoint"] = relationship(back_populates="schedule")


# ── Documents (polymorphic file store) ───────────────────────────────────────


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        # Composite index for the most common lookup: all docs for a given entity.
        Index("ix_documents_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    entity_type: Mapped[DocumentEntityType] = mapped_column(
        SAEnum(DocumentEntityType), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )  # FK enforced at app level
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)  # storage object key
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)  # original filename
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = now_utc()


# ── Audit Log ─────────────────────────────────────────────────────────────────


class AuditLog(Base):
    """Immutable record of every write operation. Never updated or deleted."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        # Supports "show audit history for booking X ordered by time" (most common query).
        Index("ix_audit_logs_booking_time", "booking_id", "created_at"),
        # Supports "show all actions by user X ordered by time".
        Index("ix_audit_logs_actor_time", "actor_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True, index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "booking.status_changed"
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    booking: Mapped[Optional["Booking"]] = relationship(back_populates="audit_logs")


# ── Notifications ─────────────────────────────────────────────────────────────


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True, index=True
    )
    type: Mapped[NotificationType] = mapped_column(SAEnum(NotificationType), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    push_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = now_utc()

    user: Mapped["User"] = relationship(back_populates="notifications")
    booking: Mapped[Optional["Booking"]] = relationship(back_populates="notifications")
