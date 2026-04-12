"""
Database models — all tables in one file for clarity.
Relationships are explicit; cascade rules are intentional.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
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
    ClearingDocsStatus,
    ContainerStatus,
    Currency,
    CustomsStatus,
    DeliveryStatus,
    DocumentEntityType,
    InvoiceStatus,
    NotificationType,
    PaymentStatus,
    PaymentType,
    PortStatus,
    POStatus,
    ShipmentStatus,
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
    shipment_memberships: Mapped[list["ShipmentUser"]] = relationship(back_populates="user")
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
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = now_utc()

    created_by_user: Mapped["User"] = relationship(back_populates="invite_tokens")


# ── Shipment + membership ─────────────────────────────────────────────────────


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = uuid_pk()
    reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    status: Mapped[ShipmentStatus] = mapped_column(
        SAEnum(ShipmentStatus), default=ShipmentStatus.DRAFT, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    # Relationships
    members: Mapped[list["ShipmentUser"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    purchase_order: Mapped[Optional["PurchaseOrder"]] = relationship(
        back_populates="shipment", uselist=False
    )
    invoice: Mapped[Optional["Invoice"]] = relationship(back_populates="shipment", uselist=False)
    payments: Mapped[list["Payment"]] = relationship(back_populates="shipment")
    bill_of_lading: Mapped[Optional["BillOfLading"]] = relationship(
        back_populates="shipment", uselist=False
    )
    clearing_docs: Mapped[Optional["ClearingDocs"]] = relationship(
        back_populates="shipment", uselist=False
    )
    delivery_points: Mapped[list["DeliveryPoint"]] = relationship(back_populates="shipment")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="shipment")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="shipment")


class ShipmentUser(Base):
    """Junction: which users have access to which shipments, and at what role."""

    __tablename__ = "shipment_users"
    __table_args__ = (UniqueConstraint("shipment_id", "user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Allows role override per shipment (e.g. someone acting as UK agent only for this job)
    role_override: Mapped[UserRole | None] = mapped_column(SAEnum(UserRole), nullable=True)
    added_at: Mapped[datetime] = now_utc()

    shipment: Mapped["Shipment"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="shipment_memberships")

    @property
    def effective_role(self) -> UserRole:
        return self.role_override if self.role_override else self.user.role


# ── Financial: PO, Invoice, Payment ──────────────────────────────────────────


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = uuid_pk()
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    po_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    po_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    total_value: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(SAEnum(Currency), nullable=False)
    status: Mapped[POStatus] = mapped_column(
        SAEnum(POStatus), default=POStatus.DRAFT, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    shipment: Mapped["Shipment"] = relationship(back_populates="purchase_order")
    document: Mapped[Optional["Document"]] = relationship(
        primaryjoin="and_(Document.entity_type=='purchase_order', foreign(Document.entity_id)==PurchaseOrder.id)",
        foreign_keys="Document.entity_id",
        uselist=False,
        viewonly=True,
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = uuid_pk()
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(SAEnum(Currency), nullable=False)
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus), default=InvoiceStatus.PENDING, nullable=False
    )
    discrepancy_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    shipment: Mapped["Shipment"] = relationship(back_populates="invoice")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = uuid_pk()
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    swift_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(SAEnum(Currency), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_type: Mapped[PaymentType] = mapped_column(SAEnum(PaymentType), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus), default=PaymentStatus.UPLOADED, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = now_utc()

    shipment: Mapped["Shipment"] = relationship(back_populates="payments")


# ── Bill of Lading + Vessel ───────────────────────────────────────────────────


class BillOfLading(Base):
    __tablename__ = "bills_of_lading"

    id: Mapped[uuid.UUID] = uuid_pk()
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
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
    gross_weight_kg: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[BLStatus] = mapped_column(
        SAEnum(BLStatus), default=BLStatus.UPLOADED, nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    shipment: Mapped["Shipment"] = relationship(back_populates="bill_of_lading")
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
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[VesselUpdateStatus] = mapped_column(SAEnum(VesselUpdateStatus), nullable=False)
    current_position_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(
        String(100), default="myshippingtracking.com", nullable=False
    )
    created_at: Mapped[datetime] = now_utc()

    vessel: Mapped["Vessel"] = relationship(back_populates="updates")


# ── Containers ────────────────────────────────────────────────────────────────


class Container(Base):
    __tablename__ = "containers"

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
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()

    bill_of_lading: Mapped["BillOfLading"] = relationship(back_populates="containers")
    customs_record: Mapped[Optional["CustomsRecord"]] = relationship(
        back_populates="container", uselist=False
    )
    delivery_assignments: Mapped[list["DeliveryContainer"]] = relationship(
        back_populates="container"
    )


# ── Clearing Docs + Customs ───────────────────────────────────────────────────


class ClearingDocs(Base):
    __tablename__ = "clearing_docs"

    id: Mapped[uuid.UUID] = uuid_pk()
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    customs_entry_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hs_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duty_rate: Mapped[Numeric | None] = mapped_column(Numeric(5, 2), nullable=True)
    estimated_duty_vat: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)
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

    shipment: Mapped["Shipment"] = relationship(back_populates="clearing_docs")


class CustomsRecord(Base):
    __tablename__ = "customs_records"

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
    duty_paid: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)
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
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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

    shipment: Mapped["Shipment"] = relationship(back_populates="delivery_points")
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
        UUID(as_uuid=True), ForeignKey("delivery_points.id", ondelete="CASCADE"), nullable=False
    )
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("containers.id", ondelete="CASCADE"), nullable=False
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

    id: Mapped[uuid.UUID] = uuid_pk()
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=True, index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "shipment.status_changed"
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = now_utc()

    shipment: Mapped[Optional["Shipment"]] = relationship(back_populates="audit_logs")


# ── Notifications ─────────────────────────────────────────────────────────────


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=True
    )
    type: Mapped[NotificationType] = mapped_column(SAEnum(NotificationType), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    push_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = now_utc()

    user: Mapped["User"] = relationship(back_populates="notifications")
    shipment: Mapped[Optional["Shipment"]] = relationship(back_populates="notifications")
