"""End-to-end tests for VesselPollService.poll_vessels_once.

Seeds the in-memory test DB with users, shipment, BL, vessel, then drives a
full poll cycle with a stubbed VesselFinderClient. Asserts on:
  - the VesselUpdate row appended each tick (always)
  - Vessel.eta updated only on material drift
  - Notification rows fired only on transitions INTO milestone statuses
  - Per-vessel error containment (one bad vessel doesn't kill the cycle)
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime

import pytest_asyncio
from sqlalchemy import select

from app.core.enums import (
    BLStatus,
    BookingStatus,
    NotificationType,
    UserRole,
    VesselStatus,
    VesselUpdateStatus,
)
from app.db.models import (
    BillOfLading,
    Booking,
    BookingUser,
    Notification,
    User,
    Vessel,
    VesselUpdate,
)
from app.integrations.vesselfinder import FleetVesselPosition
from app.services.vessel_poll_service import VesselPollService
from tests.integration.conftest import TestSession

# ── Test doubles ──────────────────────────────────────────────────────────────


class _StubClient:
    """Replaces VesselFinderClient.get_fleet_positions() with a canned response."""

    def __init__(self, positions: Iterable[FleetVesselPosition]) -> None:
        self._positions = list(positions)

    async def get_fleet_positions(self) -> list[FleetVesselPosition]:
        return list(self._positions)


def _pos(
    *,
    imo: str,
    lat: float,
    lon: float,
    navstat: int = 0,
    eta: datetime | None = None,
) -> FleetVesselPosition:
    return FleetVesselPosition(
        imo=imo,
        mmsi=int(imo) if imo.isdigit() else None,
        timestamp=datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC),
        latitude=lat,
        longitude=lon,
        course=270.0,
        speed=12.0,
        heading=270,
        navstat=navstat,
        eta=eta,
        destination="GBSOU",
    )


# Southampton port centroid — close enough triggers APPROACHING/ARRIVED.
_NEAR_SOUTHAMPTON = (50.9097, -1.4044)
# Far from any port — pure IN_TRANSIT.
_MID_OCEAN = (45.0, -20.0)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_shipment():
    """Insert one shipment + admin + customer + BL + vessel directly.

    Returns a dict of ids the test asserts against. Bypasses the API to keep
    the test focused on the poll service itself.
    """
    async with TestSession() as db:
        admin = User(
            email=f"vp-admin-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="x",
            name="VP Admin",
            role=UserRole.ADMIN,
        )
        customer = User(
            email=f"vp-cust-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="x",
            name="VP Customer",
            role=UserRole.CUSTOMER,
        )
        db.add_all([admin, customer])
        await db.flush()

        shipment = Booking(
            reference=f"VP-SHIP-{uuid.uuid4().hex[:6]}",
            status=BookingStatus.IN_TRANSIT,
            created_by=admin.id,
        )
        db.add(shipment)
        await db.flush()

        db.add_all(
            [
                BookingUser(booking_id=shipment.id, user_id=admin.id),
                BookingUser(booking_id=shipment.id, user_id=customer.id),
            ]
        )

        bl = BillOfLading(
            booking_id=shipment.id,
            bl_number=f"BL-{uuid.uuid4().hex[:8]}",
            bl_date=date(2026, 4, 1),
            shipper_name="Acme Tiles",
            consignee_name="UK Imports Ltd",
            port_of_loading="Casablanca",
            port_of_discharge="Southampton",
            container_count=2,
            commodity_description="Tiles",
            gross_weight_kg=5000,
            status=BLStatus.CONTAINERS_CREATED,
        )
        db.add(bl)
        await db.flush()

        vessel = Vessel(
            bl_id=bl.id,
            vessel_name="MV Test",
            imo_number="9321483",
            shipping_line="TestLine",
            port_of_loading="Casablanca",
            port_of_discharge="GBSOU",  # UNLOCODE for Southampton — matches our lookup
            etd=date(2026, 4, 1),
            eta=date(2026, 5, 5),
            status=VesselStatus.DEPARTED,
        )
        db.add(vessel)
        await db.commit()

        return {
            "booking_id": shipment.id,
            "vessel_id": vessel.id,
            "admin_id": admin.id,
            "customer_id": customer.id,
        }


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_poll_appends_vessel_update_for_matched_imo(seeded_shipment):
    client = _StubClient([_pos(imo="9321483", lat=_MID_OCEAN[0], lon=_MID_OCEAN[1], navstat=0)])
    service = VesselPollService(client=client)  # type: ignore[arg-type]

    async with TestSession() as db:
        summary = await service.poll_vessels_once(db)

    assert summary.polled == 1
    assert summary.updated == 1
    assert summary.skipped_no_match == 0
    assert summary.errors == 0

    async with TestSession() as db:
        updates = (
            (
                await db.execute(
                    select(VesselUpdate).where(
                        VesselUpdate.vessel_id == seeded_shipment["vessel_id"]
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(updates) == 1
    assert updates[0].source == "vesselfinder"
    assert updates[0].created_by is None  # system-generated
    assert updates[0].status == VesselUpdateStatus.IN_TRANSIT


async def test_poll_skips_when_imo_not_in_fleet(seeded_shipment):
    """Vessel exists in DB but VF returned a different IMO — must not write
    an update for the unmatched vessel."""
    client = _StubClient([_pos(imo="9999999", lat=0.0, lon=0.0, navstat=0)])
    service = VesselPollService(client=client)  # type: ignore[arg-type]

    async with TestSession() as db:
        summary = await service.poll_vessels_once(db)

    assert summary.skipped_no_match == 1
    assert summary.updated == 0

    async with TestSession() as db:
        updates = (
            (
                await db.execute(
                    select(VesselUpdate).where(
                        VesselUpdate.vessel_id == seeded_shipment["vessel_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert updates == []


async def test_poll_matches_imo_case_insensitively():
    """DB stores IMO in one case; upstream returns a different case.
    Both sides are lowercased so the match still succeeds."""
    async with TestSession() as db:
        admin = User(
            email=f"ci-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="x",
            name="CI Admin",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.flush()
        shipment = Booking(
            reference=f"CI-{uuid.uuid4().hex[:6]}",
            status=BookingStatus.IN_TRANSIT,
            created_by=admin.id,
        )
        db.add(shipment)
        await db.flush()
        bl = BillOfLading(
            booking_id=shipment.id,
            bl_number=f"BL-{uuid.uuid4().hex[:8]}",
            bl_date=date(2026, 4, 1),
            shipper_name="A",
            consignee_name="B",
            port_of_loading="Casablanca",
            port_of_discharge="GBSOU",
            container_count=1,
            commodity_description="Tiles",
            gross_weight_kg=1000,
            status=BLStatus.CONTAINERS_CREATED,
        )
        db.add(bl)
        await db.flush()
        vessel = Vessel(
            bl_id=bl.id,
            vessel_name="Case Test",
            imo_number="IMO9321999",  # stored with uppercase prefix
            shipping_line="TestLine",
            port_of_loading="Casablanca",
            port_of_discharge="GBSOU",
            etd=date(2026, 4, 1),
            eta=date(2026, 5, 10),
            status=VesselStatus.DEPARTED,
        )
        db.add(vessel)
        await db.commit()
        vessel_id = vessel.id

    # Upstream returns the same IMO in lowercase — must still match.
    client = _StubClient([_pos(imo="imo9321999", lat=_MID_OCEAN[0], lon=_MID_OCEAN[1], navstat=0)])
    service = VesselPollService(client=client)  # type: ignore[arg-type]

    async with TestSession() as db:
        summary = await service.poll_vessels_once(db)

    assert summary.polled == 1
    assert summary.skipped_no_match == 0

    async with TestSession() as db:
        updates = (
            (await db.execute(select(VesselUpdate).where(VesselUpdate.vessel_id == vessel_id)))
            .scalars()
            .all()
        )
    assert len(updates) == 1


async def test_poll_skips_vessel_with_no_imo():
    """Seed a vessel without IMO — it should be filtered by the SQL query
    (skipped_no_imo counter is for defensive in-loop checks, normally 0)."""
    async with TestSession() as db:
        admin = User(
            email=f"noimo-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="x",
            name="A",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.flush()
        shipment = Booking(
            reference=f"NOIMO-{uuid.uuid4().hex[:6]}",
            status=BookingStatus.IN_TRANSIT,
            created_by=admin.id,
        )
        db.add(shipment)
        await db.flush()
        bl = BillOfLading(
            booking_id=shipment.id,
            bl_number=f"BL-{uuid.uuid4().hex[:8]}",
            bl_date=date(2026, 4, 1),
            shipper_name="A",
            consignee_name="B",
            port_of_loading="X",
            port_of_discharge="Y",
            container_count=1,
            commodity_description="Stuff",
            gross_weight_kg=100,
        )
        db.add(bl)
        await db.flush()
        vessel = Vessel(
            bl_id=bl.id,
            vessel_name="No IMO",
            imo_number=None,  # explicit
            shipping_line="X",
            port_of_loading="Casablanca",
            port_of_discharge="GBSOU",
            status=VesselStatus.DEPARTED,
        )
        db.add(vessel)
        await db.commit()
        vessel_id = vessel.id

    client = _StubClient([])
    service = VesselPollService(client=client)  # type: ignore[arg-type]
    async with TestSession() as db:
        summary = await service.poll_vessels_once(db)

    # The SQL filter (`imo_number IS NOT NULL`) means this vessel is never
    # loaded — `polled` stays 0, no updates are written.
    assert summary.polled == 0

    async with TestSession() as db:
        updates = (
            (await db.execute(select(VesselUpdate).where(VesselUpdate.vessel_id == vessel_id)))
            .scalars()
            .all()
        )
    assert updates == []


async def test_poll_fires_notification_on_transition_to_approaching(seeded_shipment):
    # 30 nm offshore from Southampton, under way → APPROACHING
    client = _StubClient(
        [_pos(imo="9321483", lat=_NEAR_SOUTHAMPTON[0] + 0.5, lon=_NEAR_SOUTHAMPTON[1], navstat=0)]
    )
    service = VesselPollService(client=client)  # type: ignore[arg-type]

    async with TestSession() as db:
        summary = await service.poll_vessels_once(db)

    assert summary.notifications_fired == 1

    async with TestSession() as db:
        notifs = (
            (
                await db.execute(
                    select(Notification).where(
                        Notification.booking_id == seeded_shipment["booking_id"],
                        Notification.type == NotificationType.VESSEL_APPROACHING,
                    )
                )
            )
            .scalars()
            .all()
        )

    # ADMIN + CUSTOMER → 2 notification rows.
    assert len(notifs) == 2
    user_ids = {n.user_id for n in notifs}
    assert seeded_shipment["admin_id"] in user_ids
    assert seeded_shipment["customer_id"] in user_ids


async def test_no_notification_when_status_unchanged_across_polls(seeded_shipment):
    """Two consecutive ticks both APPROACHING → only one notification."""
    pos = _pos(imo="9321483", lat=_NEAR_SOUTHAMPTON[0] + 0.5, lon=_NEAR_SOUTHAMPTON[1], navstat=0)
    service = VesselPollService(client=_StubClient([pos]))  # type: ignore[arg-type]

    async with TestSession() as db:
        s1 = await service.poll_vessels_once(db)
    async with TestSession() as db:
        s2 = await service.poll_vessels_once(db)

    assert s1.notifications_fired == 1
    assert s2.notifications_fired == 0  # no transition — no spam

    async with TestSession() as db:
        notifs = (
            (
                await db.execute(
                    select(Notification).where(
                        Notification.type == NotificationType.VESSEL_APPROACHING
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(notifs) == 2  # one tick * (admin + customer)


async def test_eta_unchanged_when_drift_below_threshold(seeded_shipment):
    # Stored ETA is 2026-05-05. Push by 1 hour → < 2h threshold → no update.
    client = _StubClient(
        [
            _pos(
                imo="9321483",
                lat=_MID_OCEAN[0],
                lon=_MID_OCEAN[1],
                eta=datetime(2026, 5, 5, 1, 0, 0, tzinfo=UTC),
            )
        ]
    )
    service = VesselPollService(client=client)  # type: ignore[arg-type]

    async with TestSession() as db:
        summary = await service.poll_vessels_once(db)

    assert summary.eta_changed == 0

    async with TestSession() as db:
        vessel = await db.get(Vessel, seeded_shipment["vessel_id"])
        assert vessel.eta == date(2026, 5, 5)  # unchanged


async def test_eta_updated_when_drift_exceeds_threshold(seeded_shipment):
    # Push ETA by 3 days → well past 2h threshold → update + DELAYED status.
    revised = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
    client = _StubClient([_pos(imo="9321483", lat=_MID_OCEAN[0], lon=_MID_OCEAN[1], eta=revised)])
    service = VesselPollService(client=client)  # type: ignore[arg-type]

    async with TestSession() as db:
        summary = await service.poll_vessels_once(db)

    assert summary.eta_changed == 1

    async with TestSession() as db:
        vessel = await db.get(Vessel, seeded_shipment["vessel_id"])
        assert vessel.eta == date(2026, 5, 8)


async def test_per_vessel_error_does_not_abort_cycle(seeded_shipment, monkeypatch):
    """A second vessel in the fleet that raises during processing must not
    prevent the first vessel from being committed."""
    # Seed a second vessel that we'll cause to error.
    async with TestSession() as db:
        admin = User(
            email=f"err-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="x",
            name="X",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.flush()
        shipment = Booking(
            reference=f"ERR-{uuid.uuid4().hex[:6]}",
            status=BookingStatus.IN_TRANSIT,
            created_by=admin.id,
        )
        db.add(shipment)
        await db.flush()
        bl = BillOfLading(
            booking_id=shipment.id,
            bl_number=f"BL-{uuid.uuid4().hex[:8]}",
            bl_date=date(2026, 4, 1),
            shipper_name="A",
            consignee_name="B",
            port_of_loading="X",
            port_of_discharge="Y",
            container_count=1,
            commodity_description="Stuff",
            gross_weight_kg=100,
        )
        db.add(bl)
        await db.flush()
        bad_vessel = Vessel(
            bl_id=bl.id,
            vessel_name="Bad",
            imo_number="1111111",
            shipping_line="X",
            port_of_loading="Casablanca",
            port_of_discharge="GBSOU",
            status=VesselStatus.DEPARTED,
        )
        db.add(bad_vessel)
        await db.commit()

    # Stub the client to return positions for both. The good IMO is processed
    # normally; for the bad IMO we monkey-patch derive_status to raise.
    client = _StubClient(
        [
            _pos(imo="9321483", lat=_MID_OCEAN[0], lon=_MID_OCEAN[1]),
            _pos(imo="1111111", lat=_MID_OCEAN[0], lon=_MID_OCEAN[1]),
        ]
    )
    service = VesselPollService(client=client)  # type: ignore[arg-type]

    from app.services import vessel_poll_service as vps

    real = vps.derive_status
    call_count = {"n": 0}

    def _flaky_derive(*, position, **kwargs):
        call_count["n"] += 1
        if position.imo == "1111111":
            raise RuntimeError("boom")
        return real(position=position, **kwargs)

    monkeypatch.setattr(vps, "derive_status", _flaky_derive)

    async with TestSession() as db:
        summary = await service.poll_vessels_once(db)

    assert summary.errors == 1
    assert summary.updated == 1  # only the good vessel committed

    async with TestSession() as db:
        good_updates = (
            (
                await db.execute(
                    select(VesselUpdate).where(
                        VesselUpdate.vessel_id == seeded_shipment["vessel_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(good_updates) == 1


# ── Sanity: feature flag in beat task ─────────────────────────────────────────


def test_poll_task_no_ops_when_disabled(monkeypatch):
    """The Celery task wrapper should short-circuit when the flag is false,
    without ever touching the DB or VF client."""
    from app.background import tasks as bg_tasks
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "VESSELFINDER_ENABLED", False, raising=False)

    # Calling the underlying function (.run is the unbound impl); using the
    # task `.apply()` would try to enqueue.
    result = bg_tasks.poll_vesselfinder.run()
    assert result == {"skipped": "disabled"}
