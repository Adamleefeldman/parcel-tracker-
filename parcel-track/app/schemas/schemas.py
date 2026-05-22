"""
Pydantic schemas for request validation and response serialisation.
Financial fields are Optional[Decimal] — the service layer sets them to None
for non-admin users before returning.
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.core.enums import UKPort

# ── Base ──────────────────────────────────────────────────────────────────────


class UUIDModel(BaseModel):
    id: uuid.UUID
    model_config = {"from_attributes": True}


# ── Auth ──────────────────────────────────────────────────────────────────────


class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # UserRole value
    booking_id: uuid.UUID | None = None


class AcceptInviteRequest(BaseModel):
    token: str
    name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(UUIDModel):
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime


# ── Bookings ──────────────────────────────────────────────────────────────────


class BookingCreate(BaseModel):
    reference: str
    booking_number: str | None = None


class BookingOut(UUIDModel):
    reference: str
    booking_number: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class BookingAddMember(BaseModel):
    user_id: uuid.UUID
    role_override: str | None = None


class BookingPOLinkIn(BaseModel):
    purchase_order_id: uuid.UUID


class BookingDetailOut(BookingOut):
    """Full booking detail — used by GET /bookings/{id}. Includes all nested relationships."""

    purchase_orders: list["POOut"] = []
    payments: list["SupplierPaymentOut"] = []
    bill_of_lading: Optional["BLOut"] = None
    clearing_docs: Optional["ClearingDocsOut"] = None
    delivery_points: list["DeliveryPointOut"] = []
    legs: list["ShipmentLegOut"] = []
    # Booking-confirmation fields (P1.2)
    gate_in_cutoff: datetime | None = None
    empty_pickup_release: datetime | None = None
    empty_return_deadline: datetime | None = None
    free_days_detention: int | None = None
    free_days_demurrage: int | None = None
    detention_rate_gbp_after: Decimal | None = None
    demurrage_rate_gbp_after: Decimal | None = None
    port_of_discharge_terminal: str | None = None
    service_mode: str | None = None


class BookingUpdate(BaseModel):
    reference: str | None = None
    booking_number: str | None = None
    # Booking-confirmation fields (P1.2) — populated after the carrier's
    # Booking Confirmation PDF arrives.
    gate_in_cutoff: datetime | None = None
    empty_pickup_release: datetime | None = None
    empty_return_deadline: datetime | None = None
    free_days_detention: int | None = None
    free_days_demurrage: int | None = None
    detention_rate_gbp_after: Decimal | None = None
    demurrage_rate_gbp_after: Decimal | None = None
    port_of_discharge_terminal: str | None = None
    service_mode: str | None = None


# ── Purchase Order ─────────────────────────────────────────────────────────────


class POCreate(BaseModel):
    po_number: str
    po_date: date
    supplier_ref: str | None = None
    product_description: str
    quantity: Decimal
    quantity_unit: str
    total_value: Decimal
    currency: str
    notes: str | None = None

    @field_validator("quantity", "total_value")
    @classmethod
    def must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v


class POOut(UUIDModel):
    po_number: str
    po_date: date
    product_description: str
    quantity: Decimal
    quantity_unit: str
    total_value: Decimal | None = None  # None for non-admins
    currency: str
    status: str
    notes: str | None = None
    invoice: Optional["InvoiceOut"] = None
    created_at: datetime


# ── Invoice ───────────────────────────────────────────────────────────────────


class InvoiceCreate(BaseModel):
    invoice_number: str
    invoice_date: date
    value: Decimal
    currency: str
    payment_terms: str | None = None
    due_date: date | None = None

    @field_validator("value")
    @classmethod
    def value_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v

    @model_validator(mode="after")
    def due_date_after_invoice_date(self):
        if self.due_date is not None and self.due_date < self.invoice_date:
            raise ValueError("due_date must not be before invoice_date")
        return self


class InvoiceOut(UUIDModel):
    invoice_number: str
    invoice_date: date
    value: Decimal | None = None  # None for non-admins
    currency: str
    payment_terms: str | None = None
    due_date: date | None = None
    status: str
    discrepancy_acknowledged: bool
    created_at: datetime


# ── Supplier payment ─────────────────────────────────────────────────────────


class SupplierPaymentCreate(BaseModel):
    swift_ref: str
    payment_date: date
    amount: Decimal
    currency: str
    bank_name: str | None = None
    payment_type: str
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v


class SupplierPaymentOut(UUIDModel):
    swift_ref: str | None = None  # None for non-admins
    payment_date: date
    amount: Decimal | None = None  # None for non-admins
    currency: str
    payment_type: str
    status: str
    created_at: datetime


# ── Customer payment (inbound from broker) ───────────────────────────────────


class CustomerPaymentCreate(BaseModel):
    """Create a single tranche of an inbound customer payment for a container.

    Multi-tranche pattern: a container can take ≥1 tranche across days. The
    caller sets `tranche_index` explicitly so the bookkeeping is unambiguous.
    """

    payment_date: date
    method: str  # "cash" | "transfer"
    amount_received: Decimal  # GBP
    variance: Decimal | None = None  # signed: negative = short, positive = over
    expense_courier: Decimal | None = None
    expense_bank_charge: Decimal | None = None
    banked_total: Decimal | None = None
    sender_bank: str | None = None
    receiver_bank: str | None = None
    tranche_index: int = 1
    customer_invoice_ref: str | None = None
    notes: str | None = None

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        if v not in ("cash", "transfer"):
            raise ValueError("method must be one of: cash, transfer")
        return v

    @field_validator("amount_received")
    @classmethod
    def amount_received_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount_received must be greater than zero")
        return v

    @field_validator("expense_courier", "expense_bank_charge")
    @classmethod
    def expenses_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("Expenses must be non-negative")
        return v

    @field_validator("tranche_index")
    @classmethod
    def tranche_index_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("tranche_index must be >= 1")
        return v


class CustomerPaymentOut(UUIDModel):
    container_id: uuid.UUID
    payment_date: date
    method: str
    amount_received: Decimal | None = None  # None for non-admins
    variance: Decimal | None = None
    expense_courier: Decimal | None = None
    expense_bank_charge: Decimal | None = None
    banked_total: Decimal | None = None
    sender_bank: str | None = None
    receiver_bank: str | None = None
    tranche_index: int
    customer_invoice_ref: str | None = None
    notes: str | None = None
    created_at: datetime


# ── Bill of Lading ─────────────────────────────────────────────────────────────

CONTAINER_NUMBER_RE = re.compile(r"^[A-Z]{4}\d{7}$")


class ContainerInput(BaseModel):
    container_number: str
    seal_number: str | None = None

    @field_validator("container_number")
    @classmethod
    def validate_container_number(cls, v: str) -> str:
        if not CONTAINER_NUMBER_RE.match(v.upper()):
            raise ValueError(
                f"Invalid container number format: {v}. Expected 4 letters + 7 digits (e.g. TCKU1234567)"  # noqa: E501
            )
        return v.upper()


class BLCreate(BaseModel):
    bl_number: str
    bl_date: date
    shipper_name: str
    consignee_name: str
    notify_party: str | None = None
    port_of_loading: str
    port_of_discharge: UKPort
    containers: list[ContainerInput]
    commodity_description: str
    gross_weight_kg: Decimal

    @field_validator("gross_weight_kg")
    @classmethod
    def gross_weight_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v

    @model_validator(mode="after")
    def containers_match_count(self):
        if len(self.containers) == 0:
            raise ValueError("At least one container is required")
        # Enforce unique container numbers within a single BL submission
        numbers = [c.container_number for c in self.containers]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Duplicate container numbers in BL submission")
        return self


class BrokerOut(UUIDModel):
    code: str
    name: str
    phone: str | None = None


class CompanyOut(UUIDModel):
    legal_name: str
    aliases: list[str] | None = None
    registration_no: str | None = None
    vat_no: str | None = None
    default_address: str | None = None


class BrokerCreate(BaseModel):
    code: str
    name: str
    phone: str | None = None


class CompanyCreate(BaseModel):
    legal_name: str
    aliases: list[str] | None = None
    registration_no: str | None = None
    vat_no: str | None = None
    default_address: str | None = None


class ContainerOut(UUIDModel):
    container_number: str
    seal_number: str | None = None
    port_status: str
    status: str
    lifecycle_status: str = "ordered"
    destin8_ref: str | None = None
    notes: str | None = None
    delivery_type: str | None = None
    broker: BrokerOut | None = None
    end_company: CompanyOut | None = None
    sale_price_per_tray: Decimal | None = None
    sale_price_per_pallet: Decimal | None = None
    sale_price_total: Decimal | None = None
    sale_currency: str = "GBP"
    dispute_reason: str | None = None
    disputed_at: datetime | None = None
    updated_at: datetime


class ContainerSaleUpdate(BaseModel):
    """PATCH payload to attach sale-side data to a container."""

    delivery_type: str | None = None
    broker_id: uuid.UUID | None = None
    end_company_id: uuid.UUID | None = None
    sale_price_per_tray: Decimal | None = None
    sale_price_per_pallet: Decimal | None = None
    sale_price_total: Decimal | None = None
    sale_currency: str | None = None

    @field_validator("delivery_type")
    @classmethod
    def validate_delivery_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("direct", "via_warehouse"):
            raise ValueError("delivery_type must be one of: direct, via_warehouse")
        return v

    @field_validator("sale_price_per_tray", "sale_price_per_pallet", "sale_price_total")
    @classmethod
    def sale_prices_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("Sale price must be non-negative")
        return v


class BLOut(UUIDModel):
    bl_number: str
    bl_date: date
    shipper_name: str
    consignee_name: str
    port_of_loading: str
    port_of_discharge: UKPort
    container_count: int
    commodity_description: str
    gross_weight_kg: Decimal
    status: str
    containers: list[ContainerOut] = []
    vessel: Optional["VesselOut"] = None
    created_at: datetime


# ── Port templates (P1.3) ────────────────────────────────────────────────────


class PortTemplateUpsert(BaseModel):
    free_days_detention: int
    free_days_demurrage: int
    detention_rate_gbp_after: Decimal | None = None
    demurrage_rate_gbp_after: Decimal | None = None

    @field_validator("free_days_detention", "free_days_demurrage")
    @classmethod
    def free_days_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Free days must be >= 0")
        return v

    @field_validator("detention_rate_gbp_after", "demurrage_rate_gbp_after")
    @classmethod
    def rate_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("Rate must be >= 0")
        return v


class PortTemplateOut(UUIDModel):
    port: UKPort
    free_days_detention: int
    free_days_demurrage: int
    detention_rate_gbp_after: Decimal | None = None
    demurrage_rate_gbp_after: Decimal | None = None
    created_at: datetime
    updated_at: datetime


# ── Vessel ────────────────────────────────────────────────────────────────────


class VesselCreate(BaseModel):
    vessel_name: str
    imo_number: str | None = None
    voyage_number: str | None = None
    shipping_line: str
    port_of_loading: str
    port_of_discharge: str
    etd: date | None = None


class VesselDeparture(BaseModel):
    atd: date
    eta: date

    @model_validator(mode="after")
    def eta_after_atd(self):
        if self.eta <= self.atd:
            raise ValueError("ETA must be after ATD")
        return self


class VesselUpdateCreate(BaseModel):
    status: str
    current_position_note: str | None = None
    revised_eta: date | None = None

    @model_validator(mode="after")
    def revised_eta_required_if_delayed(self):
        if self.status == "delayed" and not self.revised_eta:
            raise ValueError("revised_eta is required when status is 'delayed'")
        return self


class VesselUpdateOut(UUIDModel):
    status: str
    current_position_note: str | None = None
    revised_eta: date | None = None
    source: str
    created_at: datetime


class VesselOut(UUIDModel):
    vessel_name: str
    imo_number: str | None = None
    shipping_line: str
    port_of_loading: str
    port_of_discharge: str
    etd: date | None = None
    atd: date | None = None
    eta: date | None = None
    status: str
    updates: list[VesselUpdateOut] = []


# ── Shipment legs (P1.1 — multi-leg routes) ──────────────────────────────────


class ShipmentLegCreate(BaseModel):
    vessel_name: str
    imo_number: str | None = None
    voyage_number: str | None = None
    shipping_line: str
    port_from: str
    port_to: str
    etd: date | None = None
    eta: date | None = None
    # Optional: when omitted the service appends the leg at the next index.
    leg_index: int | None = None

    @model_validator(mode="after")
    def leg_index_positive(self):
        if self.leg_index is not None and self.leg_index < 1:
            raise ValueError("leg_index must be >= 1")
        return self


class ShipmentLegUpdate(BaseModel):
    """All fields optional — this is how atd/ata/revised eta get set later."""

    vessel_name: str | None = None
    imo_number: str | None = None
    voyage_number: str | None = None
    shipping_line: str | None = None
    port_from: str | None = None
    port_to: str | None = None
    etd: date | None = None
    atd: date | None = None
    eta: date | None = None
    ata: date | None = None


class ShipmentLegOut(UUIDModel):
    booking_id: uuid.UUID
    leg_index: int
    vessel_name: str
    imo_number: str | None = None
    voyage_number: str | None = None
    shipping_line: str
    port_from: str
    port_to: str
    etd: date | None = None
    atd: date | None = None
    eta: date | None = None
    ata: date | None = None
    created_at: datetime
    updated_at: datetime


# ── Container status update ───────────────────────────────────────────────────


class ContainerStatusUpdate(BaseModel):
    port_status: str | None = None
    destin8_ref: str | None = None
    notes: str | None = None


# ── Customs ───────────────────────────────────────────────────────────────────


_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


class CustomsUpdate(BaseModel):
    status: str
    clearance_date: date | None = None
    hold_reason: str | None = None
    hmrc_ref: str | None = None
    duty_paid: Decimal | None = None

    @field_validator("duty_paid")
    @classmethod
    def duty_paid_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("Must be non-negative")
        return v

    @model_validator(mode="after")
    def validate_status_fields(self):
        if self.status == "cleared" and not self.clearance_date:
            raise ValueError("clearance_date required when status is 'cleared'")
        if self.status in ("on_hold", "examination") and not self.hold_reason:
            raise ValueError("hold_reason required when status is 'on_hold' or 'examination'")
        return self


class CustomsNoteCreate(BaseModel):
    note: str


class CustomsRecordOut(UUIDModel):
    status: str
    clearance_date: date | None = None
    hold_reason: str | None = None
    hmrc_ref: str | None = None
    duty_paid: Decimal | None = None
    notes: list[dict] = []
    updated_at: datetime


# ── Clearing Docs ─────────────────────────────────────────────────────────────


class ClearingDocsUpdate(BaseModel):
    customs_entry_ref: str | None = None
    hs_code: str | None = None
    duty_rate: Decimal | None = None
    estimated_duty_vat: Decimal | None = None
    has_customs_entry: bool | None = None
    has_packing_list: bool | None = None
    has_certificate_of_origin: bool | None = None
    has_health_cert: bool | None = None

    @field_validator("duty_rate", "estimated_duty_vat")
    @classmethod
    def must_be_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("Must be non-negative")
        return v


class ClearingDocsOut(UUIDModel):
    customs_entry_ref: str | None = None
    hs_code: str | None = None
    duty_rate: Decimal | None = None
    estimated_duty_vat: Decimal | None = None
    has_customs_entry: bool
    has_packing_list: bool
    has_certificate_of_origin: bool
    has_health_cert: bool
    status: str
    updated_at: datetime


# ── Delivery ──────────────────────────────────────────────────────────────────


class DeliveryPointCreate(BaseModel):
    recipient_name: str
    address: str
    contact_name: str
    contact_phone: str
    container_ids: list[uuid.UUID]
    broker_id: uuid.UUID | None = None
    end_company_id: uuid.UUID | None = None
    delivery_type: str | None = None  # "direct" | "via_warehouse"
    warehouse_name: str | None = None
    rebundled_at_warehouse: bool = False
    # Legacy field — kept for back-compat with older clients. New clients
    # should use broker_id + end_company_id instead.
    customer_user_id: uuid.UUID | None = None
    special_instructions: str | None = None

    @field_validator("delivery_type")
    @classmethod
    def validate_delivery_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("direct", "via_warehouse"):
            raise ValueError("delivery_type must be one of: direct, via_warehouse")
        return v


class DeliveryScheduleCreate(BaseModel):
    delivery_date: date
    time_window_start: str  # "07:00"
    time_window_end: str  # "12:00"
    haulier: str
    driver_name: str | None = None
    vehicle_reg: str | None = None
    notes_to_recipient: str | None = None

    @field_validator("time_window_start", "time_window_end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("Time must be in HH:MM format (e.g. '07:00')")
        return v

    @model_validator(mode="after")
    def end_after_start(self):
        if self.time_window_end <= self.time_window_start:
            raise ValueError("time_window_end must be after time_window_start")
        return self


class DeliveryStatusUpdate(BaseModel):
    status: str
    failure_reason: str | None = None

    @model_validator(mode="after")
    def failure_requires_reason(self):
        if self.status == "failed" and not self.failure_reason:
            raise ValueError("failure_reason required when status is 'failed'")
        return self


class DeliveryScheduleOut(UUIDModel):
    delivery_date: date
    time_window_start: str
    time_window_end: str
    haulier: str
    driver_name: str | None = None
    vehicle_reg: str | None = None
    notes_to_recipient: str | None = None
    status: str
    delivered_at: datetime | None = None
    failure_reason: str | None = None


class DeliveryPointOut(UUIDModel):
    recipient_name: str
    address: str
    contact_name: str
    contact_phone: str
    special_instructions: str | None = None
    status: str
    delivery_type: str | None = None
    warehouse_name: str | None = None
    rebundled_at_warehouse: bool = False
    broker: BrokerOut | None = None
    end_company: CompanyOut | None = None
    schedule: DeliveryScheduleOut | None = None
    containers: list[ContainerOut] = []
    created_at: datetime


# ── Documents ─────────────────────────────────────────────────────────────────


class UploadUrlRequest(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    file_name: str
    mime_type: str
    file_size_bytes: int | None = None

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        from app.services.storage_service import StorageService

        if v not in StorageService.ALLOWED_MIME_TYPES:
            raise ValueError(
                f"Unsupported MIME type '{v}'. "
                f"Allowed: {', '.join(sorted(StorageService.ALLOWED_MIME_TYPES))}"
            )
        return v

    @field_validator("file_size_bytes")
    @classmethod
    def validate_file_size(cls, v: int | None) -> int | None:
        from app.services.storage_service import StorageService

        if v is not None and v > StorageService.MAX_FILE_SIZE_BYTES:
            max_mb = StorageService.MAX_FILE_SIZE_BYTES // (1024 * 1024)
            raise ValueError(f"File too large ({v} bytes). Maximum allowed: {max_mb} MB")
        return v


class UploadUrlResponse(BaseModel):
    upload_url: str  # pre-signed PUT URL for client to upload to directly
    file_key: str  # key to confirm back after upload
    expires_in_seconds: int


class ConfirmUploadRequest(BaseModel):
    file_key: str
    file_name: str
    mime_type: str
    file_size_bytes: int | None = None


class DocumentOut(UUIDModel):
    entity_type: str
    entity_id: uuid.UUID
    file_name: str
    mime_type: str
    file_size_bytes: int | None = None
    download_url: str  # pre-signed GET URL, generated on request
    uploaded_at: datetime


# ── Notifications ─────────────────────────────────────────────────────────────


class NotificationOut(UUIDModel):
    type: str
    title: str
    message: str
    read: bool
    booking_id: uuid.UUID | None = None
    created_at: datetime


# ── Generic responses ─────────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    total: int
    items: list


# Resolve forward references now that all schemas are defined
BookingDetailOut.model_rebuild()
BLOut.model_rebuild()
POOut.model_rebuild()
