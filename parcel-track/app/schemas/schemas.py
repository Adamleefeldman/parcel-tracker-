"""
Pydantic schemas for request validation and response serialisation.
Financial fields are Optional[Decimal] — the service layer sets them to None
for non-admin users before returning.
"""
import uuid
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, EmailStr, field_validator, model_validator


# ── Base ──────────────────────────────────────────────────────────────────────

class UUIDModel(BaseModel):
    id: uuid.UUID
    model_config = {"from_attributes": True}


# ── Auth ──────────────────────────────────────────────────────────────────────

class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # UserRole value
    shipment_id: Optional[uuid.UUID] = None


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
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(UUIDModel):
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime


# ── Shipments ─────────────────────────────────────────────────────────────────

class ShipmentCreate(BaseModel):
    reference: str


class ShipmentOut(UUIDModel):
    reference: str
    status: str
    created_at: datetime
    updated_at: datetime


class ShipmentAddMember(BaseModel):
    user_id: uuid.UUID
    role_override: Optional[str] = None

class ShipmentUpdate(BaseModel):
    reference: Optional[str] = None
    # Extend with other editable fields (e.g. notes) if/when needed

    
# ── Purchase Order ─────────────────────────────────────────────────────────────

class POCreate(BaseModel):
    po_number: str
    po_date: date
    supplier_ref: Optional[str] = None
    product_description: str
    quantity: Decimal
    quantity_unit: str
    total_value: Decimal
    currency: str
    notes: Optional[str] = None


class POOut(UUIDModel):
    po_number: str
    po_date: date
    product_description: str
    quantity: Decimal
    quantity_unit: str
    total_value: Optional[Decimal] = None   # None for non-admins
    currency: str
    status: str
    notes: Optional[str] = None
    created_at: datetime


# ── Invoice ───────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    invoice_number: str
    invoice_date: date
    value: Decimal
    currency: str
    payment_terms: Optional[str] = None
    due_date: Optional[date] = None


class InvoiceOut(UUIDModel):
    invoice_number: str
    invoice_date: date
    value: Optional[Decimal] = None          # None for non-admins
    currency: str
    payment_terms: Optional[str] = None
    due_date: Optional[date] = None
    status: str
    discrepancy_acknowledged: bool
    created_at: datetime


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    swift_ref: str
    payment_date: date
    amount: Decimal
    currency: str
    bank_name: Optional[str] = None
    payment_type: str
    notes: Optional[str] = None


class PaymentOut(UUIDModel):
    swift_ref: Optional[str] = None         # None for non-admins
    payment_date: date
    amount: Optional[Decimal] = None        # None for non-admins
    currency: str
    payment_type: str
    status: str
    created_at: datetime


# ── Bill of Lading ─────────────────────────────────────────────────────────────

CONTAINER_NUMBER_RE = re.compile(r"^[A-Z]{4}\d{7}$")


class ContainerInput(BaseModel):
    container_number: str
    seal_number: Optional[str] = None

    @field_validator("container_number")
    @classmethod
    def validate_container_number(cls, v: str) -> str:
        if not CONTAINER_NUMBER_RE.match(v.upper()):
            raise ValueError(f"Invalid container number format: {v}. Expected 4 letters + 7 digits (e.g. TCKU1234567)")
        return v.upper()


class BLCreate(BaseModel):
    bl_number: str
    bl_date: date
    shipper_name: str
    consignee_name: str
    notify_party: Optional[str] = None
    port_of_loading: str
    port_of_discharge: str
    containers: List[ContainerInput]
    commodity_description: str
    gross_weight_kg: Decimal

    @model_validator(mode="after")
    def containers_match_count(self):
        if len(self.containers) == 0:
            raise ValueError("At least one container is required")
        # Enforce unique container numbers within a single BL submission
        numbers = [c.container_number for c in self.containers]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Duplicate container numbers in BL submission")
        return self


class ContainerOut(UUIDModel):
    container_number: str
    seal_number: Optional[str] = None
    port_status: str
    status: str
    destin8_ref: Optional[str] = None
    notes: Optional[str] = None
    updated_at: datetime


class BLOut(UUIDModel):
    bl_number: str
    bl_date: date
    shipper_name: str
    consignee_name: str
    port_of_loading: str
    port_of_discharge: str
    container_count: int
    commodity_description: str
    gross_weight_kg: Decimal
    status: str
    containers: List[ContainerOut] = []
    created_at: datetime


# ── Vessel ────────────────────────────────────────────────────────────────────

class VesselCreate(BaseModel):
    vessel_name: str
    imo_number: Optional[str] = None
    voyage_number: Optional[str] = None
    shipping_line: str
    port_of_loading: str
    port_of_discharge: str
    etd: Optional[date] = None


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
    current_position_note: Optional[str] = None
    revised_eta: Optional[date] = None

    @model_validator(mode="after")
    def revised_eta_required_if_delayed(self):
        if self.status == "delayed" and not self.revised_eta:
            raise ValueError("revised_eta is required when status is 'delayed'")
        return self


class VesselUpdateOut(UUIDModel):
    status: str
    current_position_note: Optional[str] = None
    revised_eta: Optional[date] = None
    source: str
    created_at: datetime


class VesselOut(UUIDModel):
    vessel_name: str
    imo_number: Optional[str] = None
    shipping_line: str
    port_of_loading: str
    port_of_discharge: str
    etd: Optional[date] = None
    atd: Optional[date] = None
    eta: Optional[date] = None
    status: str
    updates: List[VesselUpdateOut] = []


# ── Container status update ───────────────────────────────────────────────────

class ContainerStatusUpdate(BaseModel):
    port_status: Optional[str] = None
    destin8_ref: Optional[str] = None
    notes: Optional[str] = None


# ── Customs ───────────────────────────────────────────────────────────────────

class CustomsUpdate(BaseModel):
    status: str
    clearance_date: Optional[date] = None
    hold_reason: Optional[str] = None
    hmrc_ref: Optional[str] = None
    duty_paid: Optional[Decimal] = None

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
    clearance_date: Optional[date] = None
    hold_reason: Optional[str] = None
    hmrc_ref: Optional[str] = None
    duty_paid: Optional[Decimal] = None
    notes: List[dict] = []
    updated_at: datetime


# ── Clearing Docs ─────────────────────────────────────────────────────────────

class ClearingDocsUpdate(BaseModel):
    customs_entry_ref: Optional[str] = None
    hs_code: Optional[str] = None
    duty_rate: Optional[Decimal] = None
    estimated_duty_vat: Optional[Decimal] = None
    has_customs_entry: Optional[bool] = None
    has_packing_list: Optional[bool] = None
    has_certificate_of_origin: Optional[bool] = None
    has_health_cert: Optional[bool] = None


class ClearingDocsOut(UUIDModel):
    customs_entry_ref: Optional[str] = None
    hs_code: Optional[str] = None
    duty_rate: Optional[Decimal] = None
    estimated_duty_vat: Optional[Decimal] = None
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
    container_ids: List[uuid.UUID]
    customer_user_id: Optional[uuid.UUID] = None
    special_instructions: Optional[str] = None


class DeliveryScheduleCreate(BaseModel):
    delivery_date: date
    time_window_start: str   # "07:00"
    time_window_end: str     # "12:00"
    haulier: str
    driver_name: Optional[str] = None
    vehicle_reg: Optional[str] = None
    notes_to_recipient: Optional[str] = None


class DeliveryStatusUpdate(BaseModel):
    status: str
    failure_reason: Optional[str] = None

    @model_validator(mode="after")
    def failure_requires_reason(self):
        if self.status == "failed" and not self.failure_reason:
            raise ValueError("failure_reason required when status is 'failed'")
        return self


class DeliveryPointOut(UUIDModel):
    recipient_name: str
    address: str
    contact_name: str
    contact_phone: str
    special_instructions: Optional[str] = None
    status: str
    schedule: Optional[dict] = None
    containers: List[ContainerOut] = []
    created_at: datetime


# ── Documents ─────────────────────────────────────────────────────────────────

class UploadUrlRequest(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    file_name: str
    mime_type: str
    file_size_bytes: Optional[int] = None


class UploadUrlResponse(BaseModel):
    upload_url: str          # pre-signed PUT URL for client to upload to directly
    file_key: str            # key to confirm back after upload
    expires_in_seconds: int


class ConfirmUploadRequest(BaseModel):
    file_key: str
    file_name: str
    mime_type: str
    file_size_bytes: Optional[int] = None


class DocumentOut(UUIDModel):
    entity_type: str
    entity_id: uuid.UUID
    file_name: str
    mime_type: str
    file_size_bytes: Optional[int] = None
    download_url: str         # pre-signed GET URL, generated on request
    uploaded_at: datetime


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationOut(UUIDModel):
    type: str
    title: str
    message: str
    read: bool
    shipment_id: Optional[uuid.UUID] = None
    created_at: datetime


# ── Generic responses ─────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    total: int
    items: list
