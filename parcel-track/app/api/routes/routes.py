"""
Route definitions for all sections.
Route handlers are intentionally thin — they validate input, call a service, return output.
Business logic lives exclusively in the service layer.
"""

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import (
    RATE_LIMIT_AUTH,
    RATE_LIMIT_INVITE,
    RATE_LIMIT_REFRESH,
    RATE_LIMIT_UPLOAD,
)
from app.core.enums import (
    BLStatus,
    ClearingDocsStatus,
    ContainerStatus,
    CustomsStatus,
    DeliveryStatus,
    DocumentEntityType,
    InvoiceStatus,
    NotificationType,
    PaymentStatus,
    PortStatus,
    POStatus,
    ShipmentStatus,
    UserRole,
    VesselStatus,
    VesselUpdateStatus,
)
from app.core.exceptions import handle_integrity_error
from app.core.redis import revoke_access_token
from app.core.security import decode_access_token
from app.db.database import get_db
from app.db.models import (
    BillOfLading,
    ClearingDocs,
    Container,
    CustomsNote,
    CustomsRecord,
    DeliveryContainer,
    DeliveryPoint,
    DeliverySchedule,
    Document,
    Invoice,
    Notification,
    Payment,
    PurchaseOrder,
    Shipment,
    ShipmentUser,
    User,
    Vessel,
    VesselUpdate,
)
from app.middleware.auth import (
    financial_fields_allowed,
    get_client_ip,
    get_current_user,
    require_admin,
    require_shipment_member,
)
from app.middleware.idempotency import IdempotencyResult, require_idempotency
from app.middleware.rate_limit import limiter
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import (
    AcceptInviteRequest,
    BLCreate,
    BLOut,
    ClearingDocsOut,
    ClearingDocsUpdate,
    ConfirmUploadRequest,
    ContainerOut,
    ContainerStatusUpdate,
    CustomsNoteCreate,
    CustomsRecordOut,
    CustomsUpdate,
    DeliveryPointCreate,
    DeliveryPointOut,
    DeliveryScheduleCreate,
    DeliveryStatusUpdate,
    DocumentOut,
    InviteRequest,
    InvoiceCreate,
    InvoiceOut,
    LoginRequest,
    NotificationOut,
    PaymentCreate,
    PaymentOut,
    POCreate,
    POOut,
    RefreshRequest,
    ShipmentAddMember,
    ShipmentCreate,
    ShipmentDetailOut,
    ShipmentOut,
    ShipmentUpdate,
    UploadUrlRequest,
    UploadUrlResponse,
    VesselCreate,
    VesselDeparture,
    VesselOut,
    VesselUpdateCreate,
)
from app.services.auth_service import AuthService
from app.services.notification_service import NotificationService
from app.services.shipment_service import ShipmentService
from app.services.storage_service import StorageService

router = APIRouter()


# ════════════════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════════════════

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/invite")
@limiter.limit(RATE_LIMIT_INVITE)
async def create_invite(
    request: Request,
    body: InviteRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await AuthService.create_invite(db, body, actor)


@auth_router.post("/accept-invite")
@limiter.limit(RATE_LIMIT_INVITE)
async def accept_invite(
    request: Request,
    body: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
):
    return await AuthService.accept_invite(db, body)


@auth_router.post("/login")
@limiter.limit(RATE_LIMIT_AUTH)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    return await AuthService.login(db, body)


@auth_router.post("/refresh")
@limiter.limit(RATE_LIMIT_REFRESH)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    return await AuthService.refresh(db, body.refresh_token)


_bearer = HTTPBearer(auto_error=False)


@auth_router.post("/logout")
@limiter.limit(RATE_LIMIT_REFRESH)
async def logout(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    await AuthService.revoke_refresh(db, body.refresh_token)

    # Revoke the current access token so it cannot be reused before expiry.
    if credentials:
        payload = decode_access_token(credentials.credentials)
        if payload and (jti := payload.get("jti")):
            exp = payload.get("exp", 0)
            remaining_ttl = max(1, int(exp - datetime.now(UTC).timestamp()))
            await revoke_access_token(jti, remaining_ttl)

    return {"message": "Logged out"}


# ════════════════════════════════════════════════════════════════════════════════
# SHIPMENTS
# ════════════════════════════════════════════════════════════════════════════════

shipment_router = APIRouter(prefix="/shipments", tags=["shipments"])


@shipment_router.post("", response_model=ShipmentOut)
async def create_shipment(
    body: ShipmentCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    shipment = await ShipmentService.create(db, body.reference, actor)
    return shipment


@shipment_router.get("", response_model=PaginatedResponse[ShipmentOut])
async def list_shipments(
    status: ShipmentStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    if actor.role == UserRole.ADMIN:
        q = select(Shipment)
    else:
        q = (
            select(Shipment)
            .join(ShipmentUser, ShipmentUser.shipment_id == Shipment.id)
            .where(ShipmentUser.user_id == actor.id)
        )

    if status is not None:
        q = q.where(Shipment.status == status)
    if date_from is not None:
        q = q.where(Shipment.created_at >= date_from)
    if date_to is not None:
        q = q.where(Shipment.created_at <= date_to)

    return await paginate(db, q, pagination)


@shipment_router.get("/{shipment_id}", response_model=ShipmentDetailOut)
async def get_shipment(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    return await ShipmentService.get(db, shipment_id, actor)


@shipment_router.patch("/{shipment_id}", response_model=ShipmentOut)
async def update_shipment(
    shipment_id: uuid.UUID,
    body: ShipmentUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),  # Only admins can edit shipment metadata
):
    return await ShipmentService.update(db, shipment_id, body.model_dump(exclude_unset=True), actor)


@shipment_router.post("/{shipment_id}/members")
async def add_member(
    shipment_id: uuid.UUID,
    body: ShipmentAddMember,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    from app.core.enums import UserRole as UR
    from app.db.models import ShipmentUser

    # Gap 1 fix — verify shipment exists
    shipment_result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    if not shipment_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    # Gap 2 fix — verify user exists and is active
    user_result = await db.execute(select(User).where(User.id == body.user_id, User.is_active))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Gap 3 fix — guard against duplicate membership
    existing = await db.execute(
        select(ShipmentUser).where(
            ShipmentUser.shipment_id == shipment_id,
            ShipmentUser.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this shipment",
        )

    membership = ShipmentUser(
        shipment_id=shipment_id,
        user_id=body.user_id,
        role_override=UR(body.role_override) if body.role_override else None,
    )
    db.add(membership)
    return {"message": "Member added"}


# ════════════════════════════════════════════════════════════════════════════════
# PURCHASE ORDERS  (Admin only)
# ════════════════════════════════════════════════════════════════════════════════

po_router = APIRouter(prefix="/shipments/{shipment_id}/po", tags=["purchase-order"])


@po_router.post("", response_model=POOut)
async def create_po(
    shipment_id: uuid.UUID,
    body: POCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    existing = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.shipment_id == shipment_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "PO already exists for this shipment")

    async with handle_integrity_error("A PO with this PO number already exists"):
        po = PurchaseOrder(shipment_id=shipment_id, **body.model_dump())
        db.add(po)
        await db.flush()
    await db.refresh(po)
    return po


@po_router.patch("/{po_id}/submit")
async def submit_po(
    shipment_id: uuid.UUID,
    po_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    request: Request = None,
):
    """Mark PO as submitted — requires document already uploaded. Transitions to PO_SUBMITTED."""
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(404, "PO not found")

    # Check a document exists for this PO
    doc = await db.execute(
        select(Document).where(
            Document.entity_type == DocumentEntityType.PURCHASE_ORDER,
            Document.entity_id == po_id,
        )
    )
    if not doc.scalar_one_or_none():
        raise HTTPException(400, "Document must be uploaded before submitting PO")

    po.status = POStatus.SUBMITTED

    shipment = await ShipmentService.get(db, shipment_id, actor)
    await ShipmentService.transition_status(
        db, shipment, ShipmentStatus.PO_SUBMITTED, actor, get_client_ip(request)
    )

    await NotificationService.notify_shipment_roles(
        db, shipment_id, NotificationType.PO_SUBMITTED, [UserRole.ADMIN, UserRole.MOROCCO_AGENT]
    )
    return {"message": "PO submitted"}


@po_router.get("", response_model=POOut)
async def get_po(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.shipment_id == shipment_id))
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(404, "PO not found")

    data = POOut.model_validate(po).model_dump()
    return ShipmentService.mask_financials(data, financial_fields_allowed(actor))


# ════════════════════════════════════════════════════════════════════════════════
# INVOICE  (Admin read/write)
# ════════════════════════════════════════════════════════════════════════════════

invoice_router = APIRouter(prefix="/shipments/{shipment_id}/invoice", tags=["invoice"])


@invoice_router.post("", response_model=InvoiceOut)
async def create_invoice(
    shipment_id: uuid.UUID,
    body: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    request: Request = None,
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    # Date must be after PO date
    po_result = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.shipment_id == shipment_id)
    )
    po = po_result.scalar_one_or_none()
    if po and body.invoice_date < po.po_date:
        raise HTTPException(400, "Invoice date must be on or after PO date")

    async with handle_integrity_error("An invoice with this invoice number already exists"):
        invoice = Invoice(
            shipment_id=shipment_id, status=InvoiceStatus.RECEIVED, **body.model_dump()
        )
        db.add(invoice)
        await db.flush()

    # Check for value discrepancy vs PO (>2% triggers flag)
    if po:
        diff = abs(float(body.value) - float(po.total_value)) / float(po.total_value)
        if diff > 0.02:
            invoice.status = InvoiceStatus.DISCREPANCY

    shipment = await ShipmentService.get(db, shipment_id, actor)
    await ShipmentService.transition_status(
        db, shipment, ShipmentStatus.INVOICE_RECEIVED, actor, get_client_ip(request)
    )

    result = InvoiceOut.model_validate(invoice).model_dump(mode="json")
    await idempotency.store(result)
    return invoice


@invoice_router.patch("/{invoice_id}/acknowledge-discrepancy")
async def acknowledge_discrepancy(
    shipment_id: uuid.UUID,
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    invoice.discrepancy_acknowledged = True
    return {"message": "Discrepancy acknowledged"}


@invoice_router.get("", response_model=InvoiceOut)
async def get_invoice(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    result = await db.execute(select(Invoice).where(Invoice.shipment_id == shipment_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    data = InvoiceOut.model_validate(invoice).model_dump()
    return ShipmentService.mask_financials(data, financial_fields_allowed(actor))


# ════════════════════════════════════════════════════════════════════════════════
# PAYMENTS  (Admin only)
# ════════════════════════════════════════════════════════════════════════════════

payment_router = APIRouter(prefix="/shipments/{shipment_id}/payments", tags=["payments"])


@payment_router.post("", response_model=PaymentOut)
async def add_payment(
    shipment_id: uuid.UUID,
    body: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    request: Request = None,
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    payment = Payment(shipment_id=shipment_id, status=PaymentStatus.CONFIRMED, **body.model_dump())
    db.add(payment)
    await db.flush()

    # Check if total payments now cover the invoice
    from sqlalchemy import func

    inv_result = await db.execute(select(Invoice).where(Invoice.shipment_id == shipment_id))
    invoice = inv_result.scalar_one_or_none()
    if invoice:
        total = await db.execute(
            select(func.sum(Payment.amount)).where(
                Payment.shipment_id == shipment_id,
                Payment.status == PaymentStatus.CONFIRMED,
            )
        )
        paid = total.scalar() or 0
        if paid >= invoice.value:
            shipment = await ShipmentService.get(db, shipment_id, actor)
            if shipment.status == ShipmentStatus.INVOICE_RECEIVED:
                await ShipmentService.transition_status(
                    db, shipment, ShipmentStatus.PAYMENT_CONFIRMED, actor, get_client_ip(request)
                )
                await NotificationService.notify_shipment_roles(
                    db,
                    shipment_id,
                    NotificationType.PAYMENT_CONFIRMED,
                    [UserRole.MOROCCO_AGENT],
                )

    result = PaymentOut.model_validate(payment).model_dump(mode="json")
    await idempotency.store(result)
    return payment


@payment_router.get("", response_model=PaginatedResponse[PaymentOut])
async def list_payments(
    shipment_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    q = select(Payment).where(Payment.shipment_id == shipment_id)
    page = await paginate(db, q, pagination)
    show = financial_fields_allowed(actor)
    page["items"] = [
        ShipmentService.mask_financials(PaymentOut.model_validate(p).model_dump(), show)
        for p in page["items"]
    ]
    return page


# ════════════════════════════════════════════════════════════════════════════════
# BILL OF LADING  (Morocco agent writes, others read)
# ════════════════════════════════════════════════════════════════════════════════

bl_router = APIRouter(prefix="/shipments/{shipment_id}/bl", tags=["bill-of-lading"])


@bl_router.post("", response_model=BLOut)
async def upload_bl(
    shipment_id: uuid.UUID,
    body: BLCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    request: Request = None,
):
    if actor.role not in (UserRole.ADMIN, UserRole.MOROCCO_AGENT):
        raise HTTPException(403, "Only admin or Morocco agent can upload BL")

    async with handle_integrity_error("A BL or container number in this request already exists"):
        bl = BillOfLading(
            shipment_id=shipment_id,
            bl_number=body.bl_number,
            bl_date=body.bl_date,
            shipper_name=body.shipper_name,
            consignee_name=body.consignee_name,
            notify_party=body.notify_party,
            port_of_loading=body.port_of_loading,
            port_of_discharge=body.port_of_discharge,
            container_count=len(body.containers),
            commodity_description=body.commodity_description,
            gross_weight_kg=body.gross_weight_kg,
            status=BLStatus.UPLOADED,
        )
        db.add(bl)
        await db.flush()

        # Auto-create container records
        for c in body.containers:
            db.add(
                Container(
                    bl_id=bl.id, container_number=c.container_number, seal_number=c.seal_number
                )
            )

        bl.status = BLStatus.CONTAINERS_CREATED

    shipment = await ShipmentService.get(db, shipment_id, actor)
    await ShipmentService.transition_status(
        db, shipment, ShipmentStatus.BL_ISSUED, actor, get_client_ip(request)
    )

    await NotificationService.notify_shipment_roles(
        db, shipment_id, NotificationType.BL_UPLOADED, [UserRole.ADMIN, UserRole.UK_AGENT]
    )

    await db.flush()
    result = await db.execute(
        select(BillOfLading)
        .where(BillOfLading.id == bl.id)
        .options(
            selectinload(BillOfLading.containers),
            selectinload(BillOfLading.vessel),
        )
    )
    return result.scalar_one()


@bl_router.get("", response_model=BLOut)
async def get_bl(
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    result = await db.execute(
        select(BillOfLading)
        .where(BillOfLading.shipment_id == shipment_id)
        .options(
            selectinload(BillOfLading.containers),
            selectinload(BillOfLading.vessel).selectinload(Vessel.updates),
        )
    )
    bl = result.scalar_one_or_none()
    if not bl:
        raise HTTPException(404, "BL not found")
    return bl


# ════════════════════════════════════════════════════════════════════════════════
# VESSEL  (Morocco agent writes)
# ════════════════════════════════════════════════════════════════════════════════

vessel_router = APIRouter(prefix="/shipments/{shipment_id}/vessel", tags=["vessel"])


@vessel_router.post("", response_model=VesselOut)
async def create_vessel(
    shipment_id: uuid.UUID,
    body: VesselCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    if actor.role not in (UserRole.ADMIN, UserRole.MOROCCO_AGENT):
        raise HTTPException(403, "Only admin or Morocco agent can assign vessel")

    bl_result = await db.execute(
        select(BillOfLading).where(BillOfLading.shipment_id == shipment_id)
    )
    bl = bl_result.scalar_one_or_none()
    if not bl:
        raise HTTPException(400, "BL must be uploaded before assigning vessel")

    vessel = Vessel(bl_id=bl.id, **body.model_dump())
    db.add(vessel)
    await db.flush()
    result = await db.execute(
        select(Vessel).where(Vessel.id == vessel.id).options(selectinload(Vessel.updates))
    )
    return result.scalar_one()


@vessel_router.patch("/depart")
async def confirm_departure(
    shipment_id: uuid.UUID,
    body: VesselDeparture,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    request: Request = None,
):
    if actor.role not in (UserRole.ADMIN, UserRole.MOROCCO_AGENT):
        raise HTTPException(403, "Only admin or Morocco agent can confirm departure")

    bl_result = await db.execute(
        select(BillOfLading)
        .where(BillOfLading.shipment_id == shipment_id)
        .options(selectinload(BillOfLading.vessel))
    )
    bl = bl_result.scalar_one_or_none()
    vessel = bl.vessel if bl else None
    if not vessel:
        raise HTTPException(400, "Vessel not assigned yet")

    vessel.atd = body.atd
    vessel.eta = body.eta
    vessel.status = VesselStatus.DEPARTED

    # Update all containers on this BL to in_transit
    containers = await db.execute(select(Container).where(Container.bl_id == bl.id))
    for c in containers.scalars():
        c.status = ContainerStatus.IN_TRANSIT

    shipment = await ShipmentService.get(db, shipment_id, actor)
    await ShipmentService.transition_status(
        db, shipment, ShipmentStatus.IN_TRANSIT, actor, get_client_ip(request)
    )

    await NotificationService.notify_shipment_roles(
        db,
        shipment_id,
        NotificationType.VESSEL_DEPARTED,
        [UserRole.ADMIN, UserRole.UK_AGENT, UserRole.CUSTOMER],
    )
    return {"message": "Departure confirmed", "eta": body.eta}


@vessel_router.post("/updates", response_model=VesselOut)
async def add_vessel_update(
    shipment_id: uuid.UUID,
    body: VesselUpdateCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
    idempotency: IdempotencyResult = Depends(require_idempotency),
    request: Request = None,
):
    if idempotency.cached_response:
        return idempotency.cached_response

    bl_result = await db.execute(
        select(BillOfLading)
        .where(BillOfLading.shipment_id == shipment_id)
        .options(selectinload(BillOfLading.vessel).selectinload(Vessel.updates))
    )
    bl = bl_result.scalar_one_or_none()
    vessel = bl.vessel if bl else None
    if not vessel:
        raise HTTPException(400, "No vessel found for this shipment")

    update = VesselUpdate(
        vessel_id=vessel.id,
        created_by=actor.id,
        status=VesselUpdateStatus(body.status),
        current_position_note=body.current_position_note,
        revised_eta=body.revised_eta,
    )
    db.add(update)

    if body.revised_eta:
        vessel.eta = body.revised_eta
        await NotificationService.notify_shipment_roles(
            db,
            shipment_id,
            NotificationType.VESSEL_DELAYED,
            [UserRole.ADMIN, UserRole.UK_AGENT, UserRole.CUSTOMER],
            override_message=f"Vessel ETA revised to {body.revised_eta}",
        )

    if body.status == VesselUpdateStatus.ARRIVED.value:
        await NotificationService.notify_shipment_roles(
            db,
            shipment_id,
            NotificationType.VESSEL_ARRIVED,
            [UserRole.ADMIN, UserRole.UK_AGENT],
        )
        # Update container port status
        containers = await db.execute(select(Container).where(Container.bl_id == bl.id))
        for c in containers.scalars():
            c.port_status = PortStatus.AWAITING_CUSTOMS
            c.status = ContainerStatus.AWAITING_CUSTOMS

    await idempotency.store(VesselOut.model_validate(vessel).model_dump(mode="json"))
    return vessel


# ════════════════════════════════════════════════════════════════════════════════
# CONTAINERS  (UK agent / Admin)
# ════════════════════════════════════════════════════════════════════════════════

container_router = APIRouter(prefix="/shipments/{shipment_id}/containers", tags=["containers"])


@container_router.get("", response_model=PaginatedResponse[ContainerOut])
async def list_containers(
    shipment_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    q = (
        select(Container)
        .join(BillOfLading, Container.bl_id == BillOfLading.id)
        .where(BillOfLading.shipment_id == shipment_id)
    )
    return await paginate(db, q, pagination)


@container_router.patch("/{container_id}/port-status")
async def update_port_status(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: ContainerStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Only admin or UK agent can update container status")

    result = await db.execute(select(Container).where(Container.id == container_id))
    container = result.scalar_one_or_none()
    if not container:
        raise HTTPException(404, "Container not found")

    if body.port_status:
        container.port_status = PortStatus(body.port_status)
    if body.destin8_ref:
        container.destin8_ref = body.destin8_ref
    if body.notes:
        container.notes = body.notes

    return {"message": "Container status updated"}


# ════════════════════════════════════════════════════════════════════════════════
# CUSTOMS  (UK agent writes per container)
# ════════════════════════════════════════════════════════════════════════════════

customs_router = APIRouter(
    prefix="/shipments/{shipment_id}/containers/{container_id}/customs", tags=["customs"]
)


@customs_router.put("", response_model=CustomsRecordOut)
async def upsert_customs(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: CustomsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    request: Request = None,
):
    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Only admin or UK agent can update customs status")

    result = await db.execute(
        select(CustomsRecord)
        .where(CustomsRecord.container_id == container_id)
        .options(selectinload(CustomsRecord.notes))
    )
    record = result.scalar_one_or_none()

    if not record:
        record = CustomsRecord(container_id=container_id)
        db.add(record)
        await db.flush()

    new_status = CustomsStatus(body.status)
    record.status = new_status

    if body.clearance_date:
        record.clearance_date = body.clearance_date
    if body.hold_reason:
        record.hold_reason = body.hold_reason
    if body.hmrc_ref:
        record.hmrc_ref = body.hmrc_ref
    if body.duty_paid is not None:
        record.duty_paid = body.duty_paid

    # Update container status
    container_result = await db.execute(select(Container).where(Container.id == container_id))
    container = container_result.scalar_one_or_none()

    if new_status == CustomsStatus.CLEARED:
        container.status = ContainerStatus.CLEARED
        container.port_status = PortStatus.RELEASED
        await NotificationService.notify_shipment_roles(
            db, shipment_id, NotificationType.CONTAINER_CLEARED, [UserRole.ADMIN]
        )
        # Check if ALL containers are now cleared → transition shipment
        all_containers = await db.execute(
            select(Container)
            .join(BillOfLading, Container.bl_id == BillOfLading.id)
            .where(BillOfLading.shipment_id == shipment_id)
        )
        containers = all_containers.scalars().all()
        if all(c.status == ContainerStatus.CLEARED for c in containers):
            shipment = await ShipmentService.get(db, shipment_id, actor)
            await ShipmentService.transition_status(
                db, shipment, ShipmentStatus.CLEARED, actor, get_client_ip(request)
            )

    elif new_status in (CustomsStatus.ON_HOLD, CustomsStatus.EXAMINATION):
        container.status = ContainerStatus.ON_HOLD
        container.port_status = PortStatus.CUSTOMS_HOLD
        await NotificationService.notify_shipment_roles(
            db,
            shipment_id,
            NotificationType.CONTAINER_HOLD,
            [UserRole.ADMIN],
            override_message=(
                f"Container {container.container_number} placed on hold: {body.hold_reason}"
            ),
        )

    await db.flush()
    refreshed = await db.execute(
        select(CustomsRecord)
        .where(CustomsRecord.id == record.id)
        .options(selectinload(CustomsRecord.notes))
    )
    return refreshed.scalar_one()


@customs_router.post("/notes")
async def add_customs_note(
    shipment_id: uuid.UUID,
    container_id: uuid.UUID,
    body: CustomsNoteCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    idempotency: IdempotencyResult = Depends(require_idempotency),
):
    if idempotency.cached_response:
        return idempotency.cached_response

    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Insufficient role")

    record_result = await db.execute(
        select(CustomsRecord).where(CustomsRecord.container_id == container_id)
    )
    record = record_result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "No customs record for this container")

    db.add(CustomsNote(customs_record_id=record.id, created_by=actor.id, note=body.note))
    result = {"message": "Note added"}
    await idempotency.store(result)
    return result


# ════════════════════════════════════════════════════════════════════════════════
# CLEARING DOCS  (UK agent writes)
# ════════════════════════════════════════════════════════════════════════════════

clearing_router = APIRouter(prefix="/shipments/{shipment_id}/clearing-docs", tags=["clearing-docs"])


@clearing_router.put("", response_model=ClearingDocsOut)
async def upsert_clearing_docs(
    shipment_id: uuid.UUID,
    body: ClearingDocsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Only admin or UK agent can update clearing docs")

    result = await db.execute(select(ClearingDocs).where(ClearingDocs.shipment_id == shipment_id))
    docs = result.scalar_one_or_none()

    if not docs:
        docs = ClearingDocs(shipment_id=shipment_id, uploaded_by=actor.id)
        db.add(docs)
        await db.flush()

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(docs, field, value)

    # Recalculate status
    required = [docs.has_customs_entry, docs.has_packing_list, docs.has_certificate_of_origin]
    if all(required):
        docs.status = ClearingDocsStatus.COMPLETE
    elif any(required):
        docs.status = ClearingDocsStatus.PARTIAL

    return docs


# ════════════════════════════════════════════════════════════════════════════════
# DELIVERY  (Admin loads points, UK agent schedules)
# ════════════════════════════════════════════════════════════════════════════════

delivery_router = APIRouter(prefix="/shipments/{shipment_id}/delivery", tags=["delivery"])


@delivery_router.post("/points", response_model=DeliveryPointOut)
async def create_delivery_point(
    shipment_id: uuid.UUID,
    body: DeliveryPointCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    async with handle_integrity_error(
        "One or more containers are already assigned to a delivery point"
    ):
        point = DeliveryPoint(
            shipment_id=shipment_id,
            customer_user_id=body.customer_user_id,
            recipient_name=body.recipient_name,
            address=body.address,
            contact_name=body.contact_name,
            contact_phone=body.contact_phone,
            special_instructions=body.special_instructions,
        )
        db.add(point)
        await db.flush()

        for container_id in body.container_ids:
            db.add(DeliveryContainer(delivery_point_id=point.id, container_id=container_id))

    # Reload with all relationships eagerly — unloaded optional relationships
    # (schedule, container_assignments) raise MissingGreenlet during serialisation.
    await db.flush()
    result = await db.execute(
        select(DeliveryPoint)
        .where(DeliveryPoint.id == point.id)
        .options(
            selectinload(DeliveryPoint.schedule),
            selectinload(DeliveryPoint.container_assignments).selectinload(
                DeliveryContainer.container
            ),
        )
    )
    return result.scalar_one()


@delivery_router.get("/points", response_model=PaginatedResponse[DeliveryPointOut])
async def list_delivery_points(
    shipment_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
):
    q = select(DeliveryPoint).where(DeliveryPoint.shipment_id == shipment_id)

    # Customers only see their own delivery point
    if actor.role == UserRole.CUSTOMER:
        q = q.where(DeliveryPoint.customer_user_id == actor.id)

    q = q.options(
        selectinload(DeliveryPoint.container_assignments).selectinload(DeliveryContainer.container),
        selectinload(DeliveryPoint.schedule),
    )
    return await paginate(db, q, pagination)


@delivery_router.post("/points/{point_id}/schedule")
async def schedule_delivery(
    shipment_id: uuid.UUID,
    point_id: uuid.UUID,
    body: DeliveryScheduleCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    idempotency: IdempotencyResult = Depends(require_idempotency),
    request: Request = None,
):
    if idempotency.cached_response:
        return idempotency.cached_response

    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Only admin or UK agent can schedule delivery")

    result = await db.execute(select(DeliveryPoint).where(DeliveryPoint.id == point_id))
    point = result.scalar_one_or_none()
    if not point:
        raise HTTPException(404, "Delivery point not found")

    schedule = DeliverySchedule(delivery_point_id=point_id, **body.model_dump())
    db.add(schedule)
    point.status = DeliveryStatus.SCHEDULED

    # Notify customer
    if point.customer_user_id:
        await NotificationService.send(
            db=db,
            user_id=point.customer_user_id,
            shipment_id=shipment_id,
            notification_type=NotificationType.DELIVERY_SCHEDULED,
            override_message=(
                f"Your delivery is scheduled for {body.delivery_date}"
                f" between {body.time_window_start}-{body.time_window_end}"
            ),
        )

    resp = {"message": "Delivery scheduled"}
    await idempotency.store(resp)
    return resp


@delivery_router.patch("/points/{point_id}/status")
async def update_delivery_status(
    shipment_id: uuid.UUID,
    point_id: uuid.UUID,
    body: DeliveryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_shipment_member),
    idempotency: IdempotencyResult = Depends(require_idempotency),
    request: Request = None,
):
    if idempotency.cached_response:
        return idempotency.cached_response

    if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
        raise HTTPException(403, "Only admin or UK agent can update delivery status")

    result = await db.execute(
        select(DeliveryPoint)
        .where(DeliveryPoint.id == point_id)
        .options(selectinload(DeliveryPoint.schedule))
    )
    point = result.scalar_one_or_none()
    if not point:
        raise HTTPException(404, "Delivery point not found")

    new_status = DeliveryStatus(body.status)
    point.status = new_status

    if point.schedule:
        point.schedule.status = new_status
        if new_status == DeliveryStatus.DELIVERED:
            from datetime import datetime

            point.schedule.delivered_at = datetime.now(UTC)
        if new_status == DeliveryStatus.FAILED:
            point.schedule.failure_reason = body.failure_reason
            point.status = DeliveryStatus.AWAITING_SCHEDULE  # reset for reschedule

    # Check if all points are now delivered → complete shipment
    if new_status == DeliveryStatus.DELIVERED:
        all_points = await db.execute(
            select(DeliveryPoint).where(DeliveryPoint.shipment_id == shipment_id)
        )
        if all(p.status == DeliveryStatus.DELIVERED for p in all_points.scalars()):
            shipment = await ShipmentService.get(db, shipment_id, actor)
            await ShipmentService.transition_status(
                db, shipment, ShipmentStatus.COMPLETE, actor, get_client_ip(request)
            )

    resp = {"message": f"Delivery status updated to {new_status}"}
    await idempotency.store(resp)
    return resp


# ════════════════════════════════════════════════════════════════════════════════
# DOCUMENTS  (all roles — context-dependent access)
# ════════════════════════════════════════════════════════════════════════════════

doc_router = APIRouter(prefix="/documents", tags=["documents"])


@doc_router.post("/upload-url", response_model=UploadUrlResponse)
@limiter.limit(RATE_LIMIT_UPLOAD)
async def get_upload_url(
    request: Request,
    body: UploadUrlRequest,
    actor: User = Depends(get_current_user),
):
    """Step 1: client requests a pre-signed upload URL. Client uploads directly to storage."""
    file_key = StorageService.generate_file_key(body.entity_type, body.entity_id, body.file_name)
    upload_url = StorageService.get_upload_url(file_key, body.mime_type)
    return UploadUrlResponse(
        upload_url=upload_url,
        file_key=file_key,
        expires_in_seconds=300,
    )


@doc_router.post("/confirm", response_model=DocumentOut)
async def confirm_upload(
    entity_type: str,
    entity_id: uuid.UUID,
    body: ConfirmUploadRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """Step 2: client confirms upload completed. API records the document in DB."""
    doc = Document(
        uploaded_by=actor.id,
        entity_type=DocumentEntityType(entity_type),
        entity_id=entity_id,
        file_key=body.file_key,
        file_name=body.file_name,
        mime_type=body.mime_type,
        file_size_bytes=body.file_size_bytes,
    )
    db.add(doc)
    await db.flush()
    download_url = StorageService.get_download_url(doc.file_key)
    # Build the response dict manually: model_validate(doc) cannot produce
    # download_url because it is a computed field, not a DB column.
    return {
        "id": doc.id,
        "entity_type": doc.entity_type,
        "entity_id": doc.entity_id,
        "file_name": doc.file_name,
        "mime_type": doc.mime_type,
        "file_size_bytes": doc.file_size_bytes,
        "download_url": download_url,
        "uploaded_at": doc.uploaded_at,
    }


@doc_router.get("/{document_id}/download-url")
async def get_download_url(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"download_url": StorageService.get_download_url(doc.file_key)}


# ════════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ════════════════════════════════════════════════════════════════════════════════

notif_router = APIRouter(prefix="/notifications", tags=["notifications"])


@notif_router.get("", response_model=PaginatedResponse[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    q = select(Notification).where(Notification.user_id == actor.id)
    if unread_only:
        q = q.where(~Notification.read)
    q = q.order_by(Notification.created_at.desc())
    return await paginate(db, q, pagination)


@notif_router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == actor.id
        )
    )
    notif = result.scalar_one_or_none()
    if notif:
        notif.read = True
    return {"message": "Marked as read"}


@notif_router.patch("/push-token")
async def register_push_token(
    token: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    actor.expo_push_token = token
    return {"message": "Push token registered"}
