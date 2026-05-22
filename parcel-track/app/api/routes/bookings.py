"""Booking CRUD, membership, and PO-link routes."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import BookingStatus, UserRole
from app.db.database import get_db
from app.db.models import Booking, BookingUser, User
from app.middleware.auth import get_current_user, require_admin, require_booking_member
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import (
    BookingAddMember,
    BookingCreate,
    BookingDetailOut,
    BookingOut,
    BookingPOLinkIn,
    BookingUpdate,
    ShipmentLegOut,
)
from app.services.booking_service import BookingService

booking_router = APIRouter(prefix="/bookings", tags=["bookings"])


@booking_router.post("", response_model=BookingOut)
async def create_booking(
    body: BookingCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    booking = await BookingService.create(db, body.reference, actor)
    if body.booking_number is not None:
        booking.booking_number = body.booking_number
        await db.flush()
        await db.refresh(booking)
    return booking


@booking_router.get("", response_model=PaginatedResponse[BookingOut])
async def list_bookings(
    status: BookingStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    if actor.role == UserRole.ADMIN:
        q = select(Booking)
    else:
        q = (
            select(Booking)
            .join(BookingUser, BookingUser.booking_id == Booking.id)
            .where(BookingUser.user_id == actor.id)
        )

    if status is not None:
        q = q.where(Booking.status == status)
    if date_from is not None:
        q = q.where(Booking.created_at >= date_from)
    if date_to is not None:
        q = q.where(Booking.created_at <= date_to)

    return await paginate(db, q, pagination)


@booking_router.get("/{booking_id}", response_model=BookingDetailOut)
async def get_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_booking_member),
):
    booking = await BookingService.get(db, booking_id, actor)
    purchase_orders = [link.purchase_order for link in booking.purchase_order_links]
    # Flatten supplier payments across every linked PO's invoice — payments
    # are now per-Invoice, not per-Booking, but the booking detail view still
    # wants a single list for the financial summary.
    supplier_payments = [
        p for po in purchase_orders if po.invoice is not None for p in po.invoice.supplier_payments
    ]
    return BookingDetailOut(
        id=booking.id,
        reference=booking.reference,
        booking_number=booking.booking_number,
        status=booking.status.value,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
        purchase_orders=[_po_to_out(po) for po in purchase_orders],
        payments=[_payment_to_out(p) for p in supplier_payments],
        bill_of_lading=_bl_to_out(booking.bill_of_lading) if booking.bill_of_lading else None,
        clearing_docs=_cd_to_out(booking.clearing_docs) if booking.clearing_docs else None,
        delivery_points=[_dp_to_out(p) for p in booking.delivery_points],
        legs=[ShipmentLegOut.model_validate(leg) for leg in booking.legs],
        gate_in_cutoff=booking.gate_in_cutoff,
        empty_pickup_release=booking.empty_pickup_release,
        empty_return_deadline=booking.empty_return_deadline,
        free_days_detention=booking.free_days_detention,
        free_days_demurrage=booking.free_days_demurrage,
        detention_rate_gbp_after=booking.detention_rate_gbp_after,
        demurrage_rate_gbp_after=booking.demurrage_rate_gbp_after,
        port_of_discharge_terminal=booking.port_of_discharge_terminal,
        service_mode=booking.service_mode,
    )


@booking_router.patch("/{booking_id}", response_model=BookingOut)
async def update_booking(
    booking_id: uuid.UUID,
    body: BookingUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await BookingService.update(db, booking_id, body.model_dump(exclude_unset=True), actor)


@booking_router.post("/{booking_id}/members")
async def add_member(
    booking_id: uuid.UUID,
    body: BookingAddMember,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    booking_result = await db.execute(select(Booking).where(Booking.id == booking_id))
    if not booking_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    user_result = await db.execute(select(User).where(User.id == body.user_id, User.is_active))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = await db.execute(
        select(BookingUser).where(
            BookingUser.booking_id == booking_id,
            BookingUser.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this booking",
        )

    membership = BookingUser(
        booking_id=booking_id,
        user_id=body.user_id,
        role_override=UserRole(body.role_override) if body.role_override else None,
    )
    db.add(membership)
    return {"message": "Member added"}


@booking_router.post("/{booking_id}/purchase-orders")
async def attach_purchase_order(
    booking_id: uuid.UUID,
    body: BookingPOLinkIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """
    Link an existing PurchaseOrder to this Booking. Many-to-many so the
    same PO cannot be linked twice to the same booking, but a PO may be
    associated with multiple bookings in principle.
    """
    await BookingService.attach_purchase_order(db, booking_id, body.purchase_order_id)
    return {"message": "Purchase order linked to booking"}


# ── Internal helpers — convert ORM rows to Out schemas ──────────────────────
#
# Lives here (rather than as Pydantic .from_orm) because we need to apply
# financial masking and present a few computed fields.


def _po_to_out(po):
    from app.schemas.schemas import InvoiceOut, POOut

    data = POOut(
        id=po.id,
        po_number=po.po_number,
        po_date=po.po_date,
        product_description=po.product_description,
        quantity=po.quantity,
        quantity_unit=po.quantity_unit,
        total_value=po.total_value,
        currency=po.currency.value,
        status=po.status.value,
        notes=po.notes,
        invoice=(
            InvoiceOut(
                id=po.invoice.id,
                invoice_number=po.invoice.invoice_number,
                invoice_date=po.invoice.invoice_date,
                value=po.invoice.value,
                currency=po.invoice.currency.value,
                payment_terms=po.invoice.payment_terms,
                due_date=po.invoice.due_date,
                status=po.invoice.status.value,
                discrepancy_acknowledged=po.invoice.discrepancy_acknowledged,
                created_at=po.invoice.created_at,
            )
            if po.invoice
            else None
        ),
        created_at=po.created_at,
    )
    return data


def _container_to_out(c):
    """Construct ContainerOut, including the P0.2 sale-side fields.

    Accesses container.broker / container.end_company — relies on the caller
    to have eager-loaded those relationships if they want non-null output.
    The fields default to None when the container has no sale-side data
    attached yet (typical for containers freshly created from a BL upload).
    """
    from app.schemas.schemas import BrokerOut, CompanyOut, ContainerOut

    broker_out: BrokerOut | None = None
    if c.broker is not None:
        broker_out = BrokerOut(
            id=c.broker.id, code=c.broker.code, name=c.broker.name, phone=c.broker.phone
        )

    company_out: CompanyOut | None = None
    if c.end_company is not None:
        company_out = CompanyOut(
            id=c.end_company.id,
            legal_name=c.end_company.legal_name,
            aliases=c.end_company.aliases,
            registration_no=c.end_company.registration_no,
            vat_no=c.end_company.vat_no,
            default_address=c.end_company.default_address,
        )

    return ContainerOut(
        id=c.id,
        container_number=c.container_number,
        seal_number=c.seal_number,
        port_status=c.port_status.value,
        status=c.status.value,
        lifecycle_status=c.lifecycle_status.value,
        destin8_ref=c.destin8_ref,
        notes=c.notes,
        delivery_type=c.delivery_type.value if c.delivery_type else None,
        broker=broker_out,
        end_company=company_out,
        sale_price_per_tray=c.sale_price_per_tray,
        sale_price_per_pallet=c.sale_price_per_pallet,
        sale_price_total=c.sale_price_total,
        sale_currency=c.sale_currency.value,
        dispute_reason=c.dispute_reason,
        disputed_at=c.disputed_at,
        updated_at=c.updated_at,
    )


def _payment_to_out(p):
    from app.schemas.schemas import SupplierPaymentOut

    return SupplierPaymentOut(
        id=p.id,
        swift_ref=p.swift_ref,
        payment_date=p.payment_date,
        amount=p.amount,
        currency=p.currency.value,
        payment_type=p.payment_type.value,
        status=p.status.value,
        created_at=p.created_at,
    )


def _bl_to_out(bl):
    from app.schemas.schemas import BLOut, VesselOut, VesselUpdateOut

    return BLOut(
        id=bl.id,
        bl_number=bl.bl_number,
        bl_date=bl.bl_date,
        shipper_name=bl.shipper_name,
        consignee_name=bl.consignee_name,
        port_of_loading=bl.port_of_loading,
        port_of_discharge=bl.port_of_discharge,
        container_count=bl.container_count,
        commodity_description=bl.commodity_description,
        gross_weight_kg=bl.gross_weight_kg,
        status=bl.status.value,
        containers=[_container_to_out(c) for c in bl.containers],
        vessel=(
            VesselOut(
                id=bl.vessel.id,
                vessel_name=bl.vessel.vessel_name,
                imo_number=bl.vessel.imo_number,
                shipping_line=bl.vessel.shipping_line,
                port_of_loading=bl.vessel.port_of_loading,
                port_of_discharge=bl.vessel.port_of_discharge,
                etd=bl.vessel.etd,
                atd=bl.vessel.atd,
                eta=bl.vessel.eta,
                status=bl.vessel.status.value,
                updates=[
                    VesselUpdateOut(
                        id=u.id,
                        status=u.status.value,
                        current_position_note=u.current_position_note,
                        revised_eta=u.revised_eta,
                        source=u.source,
                        created_at=u.created_at,
                    )
                    for u in bl.vessel.updates
                ],
            )
            if bl.vessel
            else None
        ),
        created_at=bl.created_at,
    )


def _cd_to_out(cd):
    from app.schemas.schemas import ClearingDocsOut

    return ClearingDocsOut(
        id=cd.id,
        customs_entry_ref=cd.customs_entry_ref,
        hs_code=cd.hs_code,
        duty_rate=cd.duty_rate,
        estimated_duty_vat=cd.estimated_duty_vat,
        has_customs_entry=cd.has_customs_entry,
        has_packing_list=cd.has_packing_list,
        has_certificate_of_origin=cd.has_certificate_of_origin,
        has_health_cert=cd.has_health_cert,
        status=cd.status.value,
        updated_at=cd.updated_at,
    )


def _dp_to_out(dp):
    from app.schemas.schemas import (
        BrokerOut,
        CompanyOut,
        DeliveryPointOut,
        DeliveryScheduleOut,
    )

    broker_out = (
        BrokerOut(id=dp.broker.id, code=dp.broker.code, name=dp.broker.name, phone=dp.broker.phone)
        if dp.broker is not None
        else None
    )
    end_company_out = (
        CompanyOut(
            id=dp.end_company.id,
            legal_name=dp.end_company.legal_name,
            aliases=dp.end_company.aliases,
            registration_no=dp.end_company.registration_no,
            vat_no=dp.end_company.vat_no,
            default_address=dp.end_company.default_address,
        )
        if dp.end_company is not None
        else None
    )

    return DeliveryPointOut(
        id=dp.id,
        recipient_name=dp.recipient_name,
        address=dp.address,
        contact_name=dp.contact_name,
        contact_phone=dp.contact_phone,
        special_instructions=dp.special_instructions,
        status=dp.status.value,
        delivery_type=dp.delivery_type.value if dp.delivery_type else None,
        warehouse_name=dp.warehouse_name,
        rebundled_at_warehouse=dp.rebundled_at_warehouse,
        broker=broker_out,
        end_company=end_company_out,
        schedule=(
            DeliveryScheduleOut(
                id=dp.schedule.id,
                delivery_date=dp.schedule.delivery_date,
                time_window_start=dp.schedule.time_window_start,
                time_window_end=dp.schedule.time_window_end,
                haulier=dp.schedule.haulier,
                driver_name=dp.schedule.driver_name,
                vehicle_reg=dp.schedule.vehicle_reg,
                notes_to_recipient=dp.schedule.notes_to_recipient,
                status=dp.schedule.status.value,
                delivered_at=dp.schedule.delivered_at,
                failure_reason=dp.schedule.failure_reason,
            )
            if dp.schedule
            else None
        ),
        containers=[_container_to_out(a.container) for a in dp.container_assignments],
        created_at=dp.created_at,
    )
