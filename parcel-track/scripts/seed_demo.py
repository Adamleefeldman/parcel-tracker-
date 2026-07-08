#!/usr/bin/env python3
"""
Seed deterministic demo data into the ParcelTrack database.

Why this exists: ad-hoc raw-SQL seeding kept failing on Postgres enum label
case ("submitted" vs "SUBMITTED"), NOT NULL ids on junction tables, and
uuid/text casts. This script goes through the app's own SQLAlchemy ORM
models, so enum labels, UUID defaults, and server defaults are always
correct. Never hand-write seeding SQL — extend this script instead.

Every seeded row is keyed on a well-known ``DEMO-`` reference (booking
references, PO numbers, container numbers ``DEMO1000001``-style, broker code
``DEMO``, admin email ``demo-admin@thefmcghub.com``), which makes the script
idempotent: re-running finds existing rows and skips them, and ``--reset``
can find and delete exactly what was seeded (children before parents).

Usage (from parcel-track/, where .env points at the local Docker Postgres)::

    uv run python scripts/seed_demo.py                     # seed everything
    uv run python scripts/seed_demo.py --scenario basic    # one scenario
    uv run python scripts/seed_demo.py --reset             # wipe DEMO- rows, then reseed
    uv run python scripts/seed_demo.py --reset --scenario none   # wipe only

From a git worktree without its own .env, point uv at the main checkout's::

    uv run --env-file /Users/adamfeldman/parcel-tracker/parcel-track/.env \\
        python scripts/seed_demo.py

Scenarios (--scenario):
    basic              booking with PO + supplier invoice + BL + 2 fresh containers
    in-transit         booking IN_TRANSIT, vessel departed, containers at sea
    delivered-unbanked containers DELIVERED with sale prices but unbanked money
                       (feeds the A/R aging / money-risk screens)
    disputed           one container in an unacknowledged DISPUTED state
    all                all of the above (default)
    none               seed nothing (useful with --reset for a pure cleanup)

Safety: refuses to touch a non-local database (host must be localhost /
127.0.0.1 / the compose-internal alias) unless --allow-remote is passed.

Note on state fields: booking.status and container.lifecycle_status are
normally *derived* (BookingService.transition_status /
ContainerLifecycleService.recompute). Seeding sets them directly, but every
scenario is constructed so the stored values match what the state machine
and the lifecycle derivation would compute from the seeded inputs.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

# Ensure the project root is on sys.path so `app` is importable when this
# script is run directly with `uv run python scripts/seed_demo.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.enums import (
    BLStatus,
    BookingStatus,
    ContainerLifecycleStatus,
    ContainerStatus,
    Currency,
    CustomerPaymentMethod,
    CustomsStatus,
    DeliveryStatus,
    DeliveryType,
    InvoiceStatus,
    PaymentStatus,
    PortStatus,
    POStatus,
    SupplierPaymentType,
    UKPort,
    UserRole,
    VesselStatus,
)
from app.core.security import hash_password
from app.db.models import (
    AuditLog,
    BillOfLading,
    Booking,
    BookingPurchaseOrder,
    Broker,
    Company,
    Container,
    CustomerPayment,
    CustomsRecord,
    DeliveryContainer,
    DeliveryPoint,
    DeliverySchedule,
    InviteToken,
    Invoice,
    Notification,
    PurchaseOrder,
    SupplierPayment,
    User,
    Vessel,
)

DEMO_PREFIX = "DEMO-"
DEMO_ADMIN_EMAIL = "demo-admin@thefmcghub.com"
DEMO_ADMIN_PASSWORD = "demo-password-123"  # intentional plaintext — local demo data only
DEMO_BROKER_CODE = "DEMO"
DEMO_COMPANY_NAME = "DEMO Trading Co Ltd"

# Hosts we consider "local" — direct localhost plus the compose-internal
# aliases used when running inside the Docker network.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres"})

SCENARIOS = ["basic", "in-transit", "delivered-unbanked", "disputed", "all", "none"]

TODAY = date.today()  # demo dates — local-day precision is fine


@dataclass
class Summary:
    """Accumulates plain-language lines to print at the end."""

    lines: list[str] = field(default_factory=list)

    def created(self, text: str) -> None:
        self.lines.append(f"  [created] {text}")

    def skipped(self, text: str) -> None:
        self.lines.append(f"  [skipped] {text}")


# ── Safety guard ──────────────────────────────────────────────────────────────


def _db_host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except (ValueError, TypeError):
        return ""


def _is_local_host(host: str) -> bool:
    return host in _LOCAL_HOSTS or host.startswith("parcel")


def _guard_remote(db_url: str, allow_remote: bool) -> None:
    host = _db_host(db_url)
    if _is_local_host(host):
        return
    if not allow_remote:
        print(
            f"REFUSING to run: database host {host!r} is not local "
            f"(expected one of {sorted(_LOCAL_HOSTS)} or a parcel* docker alias).\n"
            "This script writes demo rows — pointing it at production is almost\n"
            "certainly a mistake. If you REALLY mean it, re-run with --allow-remote.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(
        "\n"
        "  ============================================================\n"
        f"  WARNING: seeding a REMOTE database (host: {host})\n"
        "  This will write DEMO- rows into a non-local database.\n"
        "  ============================================================\n",
        file=sys.stderr,
    )


# ── Shared fixtures (admin / broker / company) ───────────────────────────────


def _ensure_admin(session: Session, summary: Summary) -> User:
    """Reuse any existing active admin; otherwise create the DEMO admin."""
    demo = session.scalar(select(User).where(User.email == DEMO_ADMIN_EMAIL))
    if demo is not None:
        summary.skipped(f"demo admin {DEMO_ADMIN_EMAIL} already exists")
        return demo

    existing = session.scalar(
        select(User)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        .order_by(User.created_at)
        .limit(1)
    )
    if existing is not None:
        summary.skipped(f"reusing existing admin {existing.email} (password unchanged)")
        return existing

    admin = User(
        email=DEMO_ADMIN_EMAIL,
        name="Demo Admin",
        hashed_password=hash_password(DEMO_ADMIN_PASSWORD),
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin)
    session.flush()
    summary.created(f"admin user {DEMO_ADMIN_EMAIL} (password: {DEMO_ADMIN_PASSWORD})")
    return admin


def _ensure_broker(session: Session, summary: Summary) -> Broker:
    broker = session.scalar(select(Broker).where(Broker.code == DEMO_BROKER_CODE))
    if broker is not None:
        summary.skipped(f"broker {DEMO_BROKER_CODE} already exists")
        return broker
    broker = Broker(code=DEMO_BROKER_CODE, name="Demo Broker", phone="+44 7700 900000")
    session.add(broker)
    session.flush()
    summary.created(f"broker {DEMO_BROKER_CODE}")
    return broker


def _ensure_company(session: Session, summary: Summary) -> Company:
    company = session.scalar(select(Company).where(Company.legal_name == DEMO_COMPANY_NAME))
    if company is not None:
        summary.skipped(f"company {DEMO_COMPANY_NAME!r} already exists")
        return company
    company = Company(
        legal_name=DEMO_COMPANY_NAME,
        aliases=["DEMO TRADING", "DEMO CO"],
        default_address="1 Demo Way, London, E1 1AA",
    )
    session.add(company)
    session.flush()
    summary.created(f"company {DEMO_COMPANY_NAME!r}")
    return company


# ── Building blocks ───────────────────────────────────────────────────────────


def _booking_exists(session: Session, reference: str) -> bool:
    return session.scalar(select(Booking.id).where(Booking.reference == reference)) is not None


def _add_po_chain(
    session: Session,
    booking: Booking,
    *,
    po_number: str,
    invoice_number: str,
    value: Decimal,
    po_status: POStatus,
    invoice_status: InvoiceStatus,
    paid_swift_ref: str | None,
) -> PurchaseOrder:
    """PO + supplier invoice (+ optional confirmed full supplier payment),
    linked to the booking via the booking_purchase_orders junction."""
    po = PurchaseOrder(
        po_number=po_number,
        po_date=TODAY - timedelta(days=35),
        supplier_ref="SCDB-DEMO",
        product_description="Pepsi 330ml cans (24-can trays) — DEMO",
        quantity=Decimal("1980"),
        quantity_unit="trays",
        total_value=value,
        currency=Currency.USD,
        status=po_status,
    )
    session.add(po)
    session.flush()
    session.add(BookingPurchaseOrder(booking_id=booking.id, purchase_order_id=po.id))

    invoice = Invoice(
        purchase_order_id=po.id,
        invoice_number=invoice_number,
        invoice_date=TODAY - timedelta(days=32),
        value=value,
        currency=Currency.USD,
        payment_terms="TT in advance",
        due_date=TODAY - timedelta(days=25),
        status=invoice_status,
    )
    session.add(invoice)
    session.flush()

    if paid_swift_ref is not None:
        session.add(
            SupplierPayment(
                invoice_id=invoice.id,
                swift_ref=paid_swift_ref,
                payment_date=TODAY - timedelta(days=28),
                amount=value,
                currency=Currency.USD,
                bank_name="Demo Bank PLC",
                payment_type=SupplierPaymentType.FULL,
                status=PaymentStatus.CONFIRMED,
            )
        )
    return po


def _add_bl(
    session: Session,
    booking: Booking,
    *,
    bl_number: str,
    container_count: int,
    status: BLStatus = BLStatus.CONTAINERS_CREATED,
) -> BillOfLading:
    bl = BillOfLading(
        booking_id=booking.id,
        bl_number=bl_number,
        bl_date=TODAY - timedelta(days=14),
        shipper_name="SCDB (Demo Supplier)",
        consignee_name="WT Trading LLC (DEMO)",
        notify_party="The FMCG Hub (DEMO)",
        port_of_loading="Casablanca",
        port_of_discharge=UKPort.LONDON_GATEWAY,
        container_count=container_count,
        commodity_description="Soft drinks — Pepsi / Mirinda / 7Up (DEMO)",
        gross_weight_kg=Decimal("21500.00"),
        status=status,
    )
    session.add(bl)
    session.flush()
    return bl


def _add_vessel(
    session: Session,
    bl: BillOfLading,
    *,
    name: str,
    status: VesselStatus,
    etd: date | None = None,
    atd: date | None = None,
    eta: date | None = None,
    ata: date | None = None,
) -> Vessel:
    vessel = Vessel(
        bl_id=bl.id,
        vessel_name=name,
        imo_number=None,
        voyage_number="V001DEMO",
        shipping_line="Maersk",
        port_of_loading="Casablanca",
        port_of_discharge="London Gateway",
        etd=etd,
        atd=atd,
        eta=eta,
        ata=ata,
        status=status,
    )
    session.add(vessel)
    session.flush()
    return vessel


def _add_container(
    session: Session,
    bl: BillOfLading,
    *,
    number: str,
    status: ContainerStatus,
    lifecycle: ContainerLifecycleStatus,
    port_status: PortStatus = PortStatus.NOT_ARRIVED,
    sale_price_total: Decimal | None = None,
    broker: Broker | None = None,
    company: Company | None = None,
) -> Container:
    container = Container(
        bl_id=bl.id,
        container_number=number,
        seal_number=f"SEAL-{number[-7:]}",
        port_status=port_status,
        status=status,
        lifecycle_status=lifecycle,
        delivery_type=DeliveryType.DIRECT if sale_price_total is not None else None,
        broker_id=broker.id if broker else None,
        end_company_id=company.id if company else None,
        sale_price_total=sale_price_total,
        sale_currency=Currency.GBP,
    )
    session.add(container)
    session.flush()
    return container


def _add_delivered_delivery(
    session: Session,
    booking: Booking,
    containers: list[Container],
    *,
    broker: Broker,
    company: Company,
    delivered_days_ago: int,
) -> None:
    """Delivery point + junction rows + schedule, all in DELIVERED state."""
    point = DeliveryPoint(
        booking_id=booking.id,
        broker_id=broker.id,
        end_company_id=company.id,
        delivery_type=DeliveryType.DIRECT,
        recipient_name=DEMO_COMPANY_NAME,
        address="1 Demo Way, London, E1 1AA",
        contact_name="Demo Contact",
        contact_phone="+44 7700 900001",
        status=DeliveryStatus.DELIVERED,
    )
    session.add(point)
    session.flush()
    for container in containers:
        session.add(DeliveryContainer(delivery_point_id=point.id, container_id=container.id))
    session.add(
        DeliverySchedule(
            delivery_point_id=point.id,
            delivery_date=TODAY - timedelta(days=delivered_days_ago),
            time_window_start="07:00",
            time_window_end="12:00",
            haulier="Demo Haulage Ltd",
            driver_name="Demo Driver",
            vehicle_reg="DE10 MOX",
            status=DeliveryStatus.DELIVERED,
            delivered_at=datetime.now(UTC) - timedelta(days=delivered_days_ago),
        )
    )


def _add_cleared_customs(session: Session, container: Container, *, cleared_days_ago: int) -> None:
    session.add(
        CustomsRecord(
            container_id=container.id,
            status=CustomsStatus.CLEARED,
            clearance_date=TODAY - timedelta(days=cleared_days_ago),
            hmrc_ref=f"DEMO-HMRC-{container.container_number[-7:]}",
            duty_paid=Decimal("1850.00"),
        )
    )


# ── Scenarios ─────────────────────────────────────────────────────────────────
#
# Each scenario is keyed on its booking reference: if the booking already
# exists the whole scenario is skipped (idempotent re-runs).


def seed_basic(session: Session, admin: User, summary: Summary) -> None:
    """Early-stage booking: PO submitted, supplier invoice received, BL just
    issued with 2 fresh containers. Containers require a BL row (bl_id is
    NOT NULL), so the earliest seedable containers sit at BL_ISSUED."""
    reference = "DEMO-BOOK-BASIC"
    if _booking_exists(session, reference):
        summary.skipped(f"basic: booking {reference} already exists")
        return

    booking = Booking(
        reference=reference,
        booking_number="DEMO-CARRIER-0001",
        status=BookingStatus.BL_ISSUED,
        created_by=admin.id,
    )
    session.add(booking)
    session.flush()

    _add_po_chain(
        session,
        booking,
        po_number="DEMO-PO-0001",
        invoice_number="DEMO-INV-0001",
        value=Decimal("45000.00"),
        po_status=POStatus.SUBMITTED,
        invoice_status=InvoiceStatus.RECEIVED,
        paid_swift_ref=None,
    )
    bl = _add_bl(session, booking, bl_number="DEMO-BL-0001", container_count=2)
    _add_vessel(
        session,
        bl,
        name="DEMO VESSEL ATLAS",
        status=VesselStatus.ETD_SET,
        etd=TODAY + timedelta(days=7),
    )
    for number in ("DEMO1000001", "DEMO1000002"):
        _add_container(
            session,
            bl,
            number=number,
            status=ContainerStatus.VESSEL_ASSIGNED,
            lifecycle=ContainerLifecycleStatus.ORDERED,
        )
    summary.created(
        f"basic: booking {reference} (BL_ISSUED) — PO DEMO-PO-0001, invoice DEMO-INV-0001, "
        "containers DEMO1000001 + DEMO1000002 (ordered)"
    )


def seed_in_transit(session: Session, admin: User, summary: Summary) -> None:
    """Booking IN_TRANSIT: supplier fully paid, BL issued, vessel departed
    (atd set), both containers AT_SEA."""
    reference = "DEMO-BOOK-TRANSIT"
    if _booking_exists(session, reference):
        summary.skipped(f"in-transit: booking {reference} already exists")
        return

    booking = Booking(
        reference=reference,
        booking_number="DEMO-CARRIER-0002",
        status=BookingStatus.IN_TRANSIT,
        created_by=admin.id,
        free_days_detention=7,
        free_days_demurrage=5,
    )
    session.add(booking)
    session.flush()

    _add_po_chain(
        session,
        booking,
        po_number="DEMO-PO-0002",
        invoice_number="DEMO-INV-0002",
        value=Decimal("46500.00"),
        po_status=POStatus.LOCKED,
        invoice_status=InvoiceStatus.RECONCILED,
        paid_swift_ref="DEMO-SWIFT-0002",
    )
    bl = _add_bl(session, booking, bl_number="DEMO-BL-0002", container_count=2)
    _add_vessel(
        session,
        bl,
        name="DEMO VESSEL MERIDIAN",
        status=VesselStatus.DEPARTED,
        etd=TODAY - timedelta(days=10),
        atd=TODAY - timedelta(days=9),
        eta=TODAY + timedelta(days=4),
    )
    for number in ("DEMO2000001", "DEMO2000002"):
        _add_container(
            session,
            bl,
            number=number,
            status=ContainerStatus.IN_TRANSIT,
            lifecycle=ContainerLifecycleStatus.AT_SEA,
        )
    summary.created(
        f"in-transit: booking {reference} (IN_TRANSIT) — vessel DEMO VESSEL MERIDIAN departed, "
        "containers DEMO2000001 + DEMO2000002 (at_sea)"
    )


def seed_delivered_unbanked(
    session: Session, admin: User, broker: Broker, company: Company, summary: Summary
) -> None:
    """Containers DELIVERED with sale prices set but the money not banked:
    one container has no customer payment at all (lifecycle=delivered), the
    other a partial tranche (lifecycle=paid). Feeds A/R aging + money-risk."""
    reference = "DEMO-BOOK-DELIVERED"
    if _booking_exists(session, reference):
        summary.skipped(f"delivered-unbanked: booking {reference} already exists")
        return

    booking = Booking(
        reference=reference,
        booking_number="DEMO-CARRIER-0003",
        status=BookingStatus.CLEARED,
        created_by=admin.id,
        free_days_detention=7,
        free_days_demurrage=5,
    )
    session.add(booking)
    session.flush()

    _add_po_chain(
        session,
        booking,
        po_number="DEMO-PO-0003",
        invoice_number="DEMO-INV-0003",
        value=Decimal("47250.00"),
        po_status=POStatus.LOCKED,
        invoice_status=InvoiceStatus.RECONCILED,
        paid_swift_ref="DEMO-SWIFT-0003",
    )
    bl = _add_bl(
        session, booking, bl_number="DEMO-BL-0003", container_count=2, status=BLStatus.LOCKED
    )
    _add_vessel(
        session,
        bl,
        name="DEMO VESSEL HORIZON",
        status=VesselStatus.DEPARTED,
        etd=TODAY - timedelta(days=41),
        atd=TODAY - timedelta(days=40),
        eta=TODAY - timedelta(days=26),
        ata=TODAY - timedelta(days=25),
    )
    unpaid = _add_container(
        session,
        bl,
        number="DEMO3000001",
        status=ContainerStatus.DELIVERED,
        lifecycle=ContainerLifecycleStatus.DELIVERED,
        port_status=PortStatus.RELEASED,
        sale_price_total=Decimal("42000.00"),
        broker=broker,
        company=company,
    )
    partial = _add_container(
        session,
        bl,
        number="DEMO3000002",
        status=ContainerStatus.DELIVERED,
        lifecycle=ContainerLifecycleStatus.PAID,
        port_status=PortStatus.RELEASED,
        sale_price_total=Decimal("43500.00"),
        broker=broker,
        company=company,
    )
    for container in (unpaid, partial):
        _add_cleared_customs(session, container, cleared_days_ago=20)
    _add_delivered_delivery(
        session, booking, [unpaid, partial], broker=broker, company=company, delivered_days_ago=18
    )
    # Partial tranche on the second container: received + banked, but well
    # short of sale_price_total → lifecycle stays PAID, not BANKED.
    session.add(
        CustomerPayment(
            container_id=partial.id,
            payment_date=TODAY - timedelta(days=10),
            method=CustomerPaymentMethod.TRANSFER,
            amount_received=Decimal("20000.00"),
            expense_bank_charge=Decimal("40.00"),
            banked_total=Decimal("19960.00"),
            sender_bank="Demo Buyer Bank",
            receiver_bank="Demo Bank PLC",
            tranche_index=1,
            customer_invoice_ref="DEMO-CINV-0003",
        )
    )
    summary.created(
        f"delivered-unbanked: booking {reference} (CLEARED) — DEMO3000001 delivered/unpaid "
        "(GBP 42,000 outstanding), DEMO3000002 part-paid GBP 20,000 of 43,500"
    )


def seed_disputed(
    session: Session, admin: User, broker: Broker, company: Company, summary: Summary
) -> None:
    """One delivered container flipped to DISPUTED (unacknowledged), which
    blocks the parent booking from ever reaching COMPLETE."""
    reference = "DEMO-BOOK-DISPUTED"
    if _booking_exists(session, reference):
        summary.skipped(f"disputed: booking {reference} already exists")
        return

    booking = Booking(
        reference=reference,
        booking_number="DEMO-CARRIER-0004",
        status=BookingStatus.CLEARED,
        created_by=admin.id,
    )
    session.add(booking)
    session.flush()

    _add_po_chain(
        session,
        booking,
        po_number="DEMO-PO-0004",
        invoice_number="DEMO-INV-0004",
        value=Decimal("23500.00"),
        po_status=POStatus.LOCKED,
        invoice_status=InvoiceStatus.RECONCILED,
        paid_swift_ref="DEMO-SWIFT-0004",
    )
    bl = _add_bl(
        session, booking, bl_number="DEMO-BL-0004", container_count=1, status=BLStatus.LOCKED
    )
    _add_vessel(
        session,
        bl,
        name="DEMO VESSEL AURORA",
        status=VesselStatus.DEPARTED,
        etd=TODAY - timedelta(days=30),
        atd=TODAY - timedelta(days=29),
        eta=TODAY - timedelta(days=15),
        ata=TODAY - timedelta(days=14),
    )
    container = _add_container(
        session,
        bl,
        number="DEMO4000001",
        status=ContainerStatus.DELIVERED,
        lifecycle=ContainerLifecycleStatus.DISPUTED,
        port_status=PortStatus.RELEASED,
        sale_price_total=Decimal("21500.00"),
        broker=broker,
        company=company,
    )
    # Dispute markers drive the DISPUTED derivation; acknowledgement fields
    # stay NULL so the dispute is "open" (blocks booking COMPLETE).
    container.dispute_reason = "Customer claims 2 pallets short-delivered (DEMO)"
    container.disputed_at = datetime.now(UTC) - timedelta(days=5)
    _add_cleared_customs(session, container, cleared_days_ago=12)
    _add_delivered_delivery(
        session, booking, [container], broker=broker, company=company, delivered_days_ago=9
    )
    summary.created(
        f"disputed: booking {reference} (CLEARED) — container DEMO4000001 DISPUTED, "
        "unacknowledged (blocks COMPLETE)"
    )


# ── Reset ─────────────────────────────────────────────────────────────────────


def reset_demo_rows(session: Session, summary: Summary) -> None:
    """Delete previously seeded DEMO- rows, children before parents.

    Most children hang off bookings/BLs/containers with ON DELETE CASCADE,
    so deleting the demo bookings takes the whole tree with it. The rows
    that need explicit handling are the ones with plain (no-cascade) FKs:
    audit logs + notifications referencing demo bookings, and anything
    referencing the demo admin user.
    """
    booking_ids = list(
        session.scalars(select(Booking.id).where(Booking.reference.like(f"{DEMO_PREFIX}%")))
    )
    if booking_ids:
        session.execute(delete(Notification).where(Notification.booking_id.in_(booking_ids)))
        session.execute(delete(AuditLog).where(AuditLog.booking_id.in_(booking_ids)))
        # Cascades: BL → vessel + containers → customs / customer payments;
        # booking → delivery points → junctions + schedules; booking → PO links.
        session.execute(delete(Booking).where(Booking.id.in_(booking_ids)))

    # POs survive booking deletion (junction-only link) — delete by DEMO- number.
    # Cascades: invoice → supplier payments.
    session.execute(delete(PurchaseOrder).where(PurchaseOrder.po_number.like(f"{DEMO_PREFIX}%")))

    # Demo containers are gone with their BLs, so the broker/company are free.
    session.execute(delete(Broker).where(Broker.code == DEMO_BROKER_CODE))
    session.execute(delete(Company).where(Company.legal_name == DEMO_COMPANY_NAME))

    # Only the DEMO admin is ever deleted — pre-existing admins are untouched.
    demo_user_id = session.scalar(select(User.id).where(User.email == DEMO_ADMIN_EMAIL))
    if demo_user_id is not None:
        session.execute(delete(AuditLog).where(AuditLog.actor_id == demo_user_id))
        session.execute(delete(InviteToken).where(InviteToken.created_by == demo_user_id))
        session.execute(delete(User).where(User.id == demo_user_id))

    summary.lines.append(
        f"  [reset]   removed {len(booking_ids)} demo booking(s) and all dependent DEMO- rows"
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def run(scenario: str, reset: bool, allow_remote: bool) -> int:
    db_url = get_settings().DATABASE_URL_SYNC
    _guard_remote(db_url, allow_remote)

    engine = create_engine(db_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    summary = Summary()

    with session_factory() as session:
        if reset:
            reset_demo_rows(session, summary)

        if scenario != "none":
            admin = _ensure_admin(session, summary)
            broker = _ensure_broker(session, summary)
            company = _ensure_company(session, summary)

            if scenario in ("basic", "all"):
                seed_basic(session, admin, summary)
            if scenario in ("in-transit", "all"):
                seed_in_transit(session, admin, summary)
            if scenario in ("delivered-unbanked", "all"):
                seed_delivered_unbanked(session, admin, broker, company, summary)
            if scenario in ("disputed", "all"):
                seed_disputed(session, admin, broker, company, summary)

            login_email = admin.email

        session.commit()

    host = _db_host(db_url)
    print(f"\nDemo seed complete against {host} (scenario: {scenario}):\n")
    print("\n".join(summary.lines))
    if scenario != "none":
        print(
            f"\n  Log in with: {login_email}"
            + (
                f" / {DEMO_ADMIN_PASSWORD}"
                if login_email == DEMO_ADMIN_EMAIL
                else " (existing admin — password unchanged)"
            )
        )
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed idempotent DEMO- data into the local ParcelTrack database."
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="all",
        help="which demo scenario to seed (default: all; 'none' seeds nothing)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete previously seeded DEMO- rows first (then seed, unless --scenario none)",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="override the local-database safety guard (DANGEROUS)",
    )
    args = parser.parse_args(argv)
    return run(args.scenario, args.reset, args.allow_remote)


if __name__ == "__main__":
    sys.exit(main())
