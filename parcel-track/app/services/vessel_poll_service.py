"""Vessel polling service — turns VesselFinder AIS snapshots into
domain state changes (`VesselUpdate` rows, `Vessel.eta` updates,
notifications).

Lives in the service layer so all business logic stays out of
`app/background/tasks.py`. The Celery task is a thin shell around
`poll_vessels_once`.

Algorithm (one pass):
    1. Load every Vessel with status ∈ {DEPARTED, ETD_SET} and a non-null
       imo_number, plus its most recent prior VesselUpdate (so we can
       detect status transitions).
    2. Fetch the full fleet from VesselFinder (one bulk call).
    3. For each matched vessel:
         a. Always append a new VesselUpdate (append-only log).
         b. If the revised ETA differs from the stored ETA by more than
            VESSELFINDER_ETA_CHANGE_THRESHOLD_HOURS, update Vessel.eta.
         c. If the derived status flipped INTO {APPROACHING, ARRIVED,
            DELAYED} (i.e. the previous VesselUpdate.status was different),
            notify ADMIN + CUSTOMER for the vessel's shipment.
    4. Commit per-vessel so a mid-cycle crash doesn't lose all work.

Why we don't write AuditLog rows here:
    AuditLog requires a non-null actor_id. There is no acting user for
    a background pull. The VesselUpdate row is itself the audit record
    for vessel events (append-only, sourced, timestamped); duplicating
    it on AuditLog would add noise without adding information. ETA
    updates are surfaced via structured logs at INFO level instead.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.enums import (
    NotificationType,
    UserRole,
    VesselStatus,
    VesselUpdateStatus,
)
from app.db.models import BillOfLading, Vessel, VesselUpdate
from app.integrations.vesselfinder import (
    FleetVesselPosition,
    VesselFinderClient,
)
from app.services.notification_service import NotificationService

if TYPE_CHECKING:
    pass

logger = logging.getLogger("parceltrack.services.vessel_poll")

# AIS NAVSTAT codes that mean the vessel is stationary in port-like conditions.
#   1 = at anchor
#   5 = moored
#   6 = aground
# Combined with proximity to the discharge port these strongly imply ARRIVED.
_STATIONARY_NAVSTATS: frozenset[int] = frozenset({1, 5, 6})

# Notifications fire only on transitions into one of these statuses (per the
# user's spec — keeps push volume sane). Other transitions are still recorded
# on VesselUpdate but are silent.
_NOTIFY_STATUSES: frozenset[VesselUpdateStatus] = frozenset(
    {
        VesselUpdateStatus.APPROACHING,
        VesselUpdateStatus.ARRIVED,
        VesselUpdateStatus.DELAYED,
    }
)


# UNLOCODE → (lat, lon) for the ports we actually use. Hardcoded because:
#   - It's a tiny static list (extend on demand).
#   - VesselFinder offers a Ports API but it costs credits per lookup.
#   - This eliminates a remote dependency from the poll path.
# Coordinates are port-centroid degrees (WGS-84). Add new ports here when the
# business expands routes.
_PORT_COORDS: dict[str, tuple[float, float]] = {
    # Morocco
    "MACAS": (33.6066, -7.6182),  # Casablanca
    "MATNG": (35.7595, -5.8000),  # Tangier (Tanger Med)
    "MAAGA": (30.4278, -9.5981),  # Agadir
    # United Kingdom
    "GBFXT": (51.9540, 1.3500),  # Felixstowe
    "GBSOU": (50.9097, -1.4044),  # Southampton
    "GBTIL": (51.4622, 0.3700),  # Tilbury
    "GBLGP": (51.5045, 0.4855),  # London Gateway
    "GBLIV": (53.4406, -3.0006),  # Liverpool
}


@dataclass(slots=True)
class PollSummary:
    """Result of one poll cycle — used for logging + future metrics."""

    polled: int = 0
    updated: int = 0
    eta_changed: int = 0
    notifications_fired: int = 0
    skipped_no_imo: int = 0
    skipped_no_match: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "polled": self.polled,
            "updated": self.updated,
            "eta_changed": self.eta_changed,
            "notifications_fired": self.notifications_fired,
            "skipped_no_imo": self.skipped_no_imo,
            "skipped_no_match": self.skipped_no_match,
            "errors": self.errors,
        }


def _haversine_nm(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points in nautical miles.

    Standard haversine. ~6 nm precision over the typical 0-10,000 nm range,
    plenty for "is the vessel within 50 nm of port?" checks.
    """
    earth_radius_nm = 3440.065  # 6371 km / 1.852 km per nm
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth_radius_nm * math.asin(math.sqrt(h))


def _port_coords(port_code: str | None) -> tuple[float, float] | None:
    """Look up port coordinates by UNLOCODE. Case-insensitive, whitespace-tolerant."""
    if not port_code:
        return None
    return _PORT_COORDS.get(port_code.strip().upper())


def _hours_between(a: datetime, b: datetime) -> float:
    """Absolute hour delta between two timezone-aware datetimes."""
    if a.tzinfo is None:
        a = a.replace(tzinfo=UTC)
    if b.tzinfo is None:
        b = b.replace(tzinfo=UTC)
    return abs((a - b).total_seconds()) / 3600.0


def _signed_hours_after(later: datetime, earlier: datetime) -> float:
    """How many hours `later` is after `earlier`. Negative if earlier is later."""
    if later.tzinfo is None:
        later = later.replace(tzinfo=UTC)
    if earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=UTC)
    return (later - earlier).total_seconds() / 3600.0


def derive_status(
    *,
    position: FleetVesselPosition,
    discharge_port_code: str,
    stored_eta: datetime | None,
    approaching_radius_nm: float,
    delayed_threshold_hours: float,
) -> VesselUpdateStatus:
    """Derive a domain status from VF's NAVSTAT + position + ETA drift.

    Precedence (highest first):
      ARRIVED      — stationary AIS code AND within port radius
      APPROACHING  — within port radius (regardless of NAVSTAT)
      DELAYED      — revised ETA materially later than stored ETA
      IN_TRANSIT   — default

    Pure function; testable without a DB or Redis.
    """
    port = _port_coords(discharge_port_code)
    near_port = False
    if port and position.latitude is not None and position.longitude is not None:
        distance_nm = _haversine_nm((position.latitude, position.longitude), port)
        near_port = distance_nm <= approaching_radius_nm

    if near_port and position.navstat in _STATIONARY_NAVSTATS:
        return VesselUpdateStatus.ARRIVED

    if near_port:
        return VesselUpdateStatus.APPROACHING

    if stored_eta is not None and position.eta is not None:
        slip_hours = _signed_hours_after(position.eta, stored_eta)
        if slip_hours > delayed_threshold_hours:
            return VesselUpdateStatus.DELAYED

    return VesselUpdateStatus.IN_TRANSIT


def _position_note(position: FleetVesselPosition) -> str | None:
    """Compact position summary persisted on VesselUpdate for ops debugging.

    None when we have nothing meaningful to record. Otherwise something like
    'lat=51.95, lon=1.35, speed=12.4kn, course=287°, navstat=0'.
    """
    parts: list[str] = []
    if position.latitude is not None and position.longitude is not None:
        parts.append(f"lat={position.latitude:.4f}, lon={position.longitude:.4f}")
    if position.speed is not None:
        parts.append(f"speed={position.speed:.1f}kn")
    if position.course is not None:
        parts.append(f"course={position.course:.0f}°")
    if position.navstat is not None:
        parts.append(f"navstat={position.navstat}")
    return ", ".join(parts) if parts else None


_NOTIFICATION_BY_STATUS: dict[VesselUpdateStatus, NotificationType] = {
    VesselUpdateStatus.APPROACHING: NotificationType.VESSEL_APPROACHING,
    VesselUpdateStatus.ARRIVED: NotificationType.VESSEL_ARRIVED,
    VesselUpdateStatus.DELAYED: NotificationType.VESSEL_DELAYED,
}


class VesselPollService:
    """Orchestration for one poll cycle.

    Constructed with an optional pre-built client so tests can inject an
    httpx.MockTransport. Production callers don't pass anything.
    """

    def __init__(self, client: VesselFinderClient | None = None) -> None:
        self._client = client or VesselFinderClient()

    async def poll_vessels_once(self, db: AsyncSession) -> PollSummary:
        """Run one poll cycle. Commits incrementally per vessel."""
        settings = get_settings()
        summary = PollSummary()

        # ── Fetch upstream once ───────────────────────────────────────────────
        positions = await self._client.get_fleet_positions()
        # Index by IMO for O(1) match lookups. Lower-cased + stripped to be
        # tolerant of upstream whitespace / case drift.
        positions_by_imo: dict[str, FleetVesselPosition] = {
            p.imo.strip().lower(): p for p in positions if p.imo
        }

        # ── Find candidate vessels ────────────────────────────────────────────
        # We want vessels that are mid-voyage (DEPARTED or ETD_SET) and have an
        # IMO we can match. Eager-load the BL → shipment chain and the most
        # recent prior VesselUpdate so the loop body never lazy-loads.
        result = await db.execute(
            select(Vessel)
            .where(
                Vessel.status.in_([VesselStatus.DEPARTED, VesselStatus.ETD_SET]),
                Vessel.imo_number.is_not(None),
            )
            .options(
                selectinload(Vessel.bill_of_lading).selectinload(BillOfLading.shipment),
                selectinload(Vessel.updates),
            )
        )
        vessels = result.scalars().all()

        for vessel in vessels:
            try:
                await self._process_vessel(
                    db=db,
                    vessel=vessel,
                    positions_by_imo=positions_by_imo,
                    summary=summary,
                    settings=settings,
                )
                # Commit per-vessel so a later crash doesn't lose earlier work.
                await db.commit()
            except Exception:
                summary.errors += 1
                logger.exception(
                    "vessel_poll_per_vessel_error",
                    extra={"vessel_id": str(vessel.id), "imo": vessel.imo_number},
                )
                await db.rollback()

        logger.info("vessel_poll_cycle_complete", extra=summary.as_dict())
        return summary

    async def _process_vessel(
        self,
        *,
        db: AsyncSession,
        vessel: Vessel,
        positions_by_imo: dict[str, FleetVesselPosition],
        summary: PollSummary,
        settings: Settings,
    ) -> None:
        if not vessel.imo_number:
            # Defensive: the query already filters, but keep this honest.
            summary.skipped_no_imo += 1
            return

        position = positions_by_imo.get(vessel.imo_number.strip().lower())
        if position is None:
            # The vessel exists in our DB with a DEPARTED/ETD_SET status but
            # is not in the VesselFinder fleet. Almost always means ops needs
            # to add the IMO to the fleet via the VF dashboard.
            summary.skipped_no_match += 1
            logger.warning(
                "vessel_not_in_vf_fleet",
                extra={
                    "vessel_id": str(vessel.id),
                    "imo": vessel.imo_number,
                },
            )
            return

        summary.polled += 1

        # ── Derive new status ─────────────────────────────────────────────────
        # Vessel.eta is a `date` (no time component). Convert to UTC midnight
        # so the threshold comparison has a defined zero point. This will
        # systematically under-report tiny slips (< 24h within the same day)
        # but the threshold default is 24h so that's a wash.
        stored_eta_dt: datetime | None = (
            datetime.combine(vessel.eta, datetime.min.time(), tzinfo=UTC)
            if vessel.eta is not None
            else None
        )
        new_status = derive_status(
            position=position,
            discharge_port_code=vessel.port_of_discharge,
            stored_eta=stored_eta_dt,
            approaching_radius_nm=settings.VESSELFINDER_APPROACHING_RADIUS_NM,
            delayed_threshold_hours=settings.VESSELFINDER_DELAYED_THRESHOLD_HOURS,
        )

        # ── Append VesselUpdate (always) ──────────────────────────────────────
        # Find the previous status BEFORE the insert so the transition check
        # is correct. `vessel.updates` is ordered by created_at ASC.
        prior_status: VesselUpdateStatus | None = (
            vessel.updates[-1].status if vessel.updates else None
        )

        update_row = VesselUpdate(
            vessel_id=vessel.id,
            created_by=None,  # system-generated
            status=new_status,
            current_position_note=_position_note(position),
            revised_eta=position.eta.date() if position.eta else None,
            source="vesselfinder",
        )
        db.add(update_row)
        summary.updated += 1

        # ── Conditionally update Vessel.eta ───────────────────────────────────
        if (
            position.eta is not None
            and stored_eta_dt is not None
            and _hours_between(position.eta, stored_eta_dt)
            >= settings.VESSELFINDER_ETA_CHANGE_THRESHOLD_HOURS
        ):
            old_eta = vessel.eta
            vessel.eta = position.eta.date()
            summary.eta_changed += 1
            logger.info(
                "vessel_eta_updated",
                extra={
                    "vessel_id": str(vessel.id),
                    "imo": vessel.imo_number,
                    "old_eta": str(old_eta),
                    "new_eta": str(vessel.eta),
                    "source": "vesselfinder",
                },
            )
        elif position.eta is not None and stored_eta_dt is None:
            # No prior ETA to compare against — adopt the upstream value.
            vessel.eta = position.eta.date()
            summary.eta_changed += 1

        # ── Conditionally fire notifications ──────────────────────────────────
        # Only on a transition INTO a milestone status. If we've been sitting
        # at APPROACHING for the last three ticks we don't keep nagging.
        if new_status in _NOTIFY_STATUSES and new_status != prior_status:
            shipment_id = vessel.bill_of_lading.shipment_id
            notif_type = _NOTIFICATION_BY_STATUS[new_status]
            await NotificationService.notify_shipment_roles(
                db=db,
                shipment_id=shipment_id,
                notification_type=notif_type,
                roles=[UserRole.ADMIN, UserRole.CUSTOMER],
            )
            summary.notifications_fired += 1
