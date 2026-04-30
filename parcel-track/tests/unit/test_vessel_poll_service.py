"""Unit tests for the pure helpers in app/services/vessel_poll_service.py.

End-to-end DB-backed tests for `poll_vessels_once` live in
`tests/integration/test_vessel_poll.py`. This file covers the deterministic
math + status-derivation logic that doesn't need a DB.
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "x" * 64)

from datetime import UTC, datetime, timedelta

from app.core.enums import VesselUpdateStatus
from app.integrations.vesselfinder import FleetVesselPosition
from app.services import vessel_poll_service as vps
from app.services.vessel_poll_service import (
    _haversine_nm,
    _hours_between,
    _port_coords,
    _signed_hours_after,
    derive_status,
)

# ── Distance math ─────────────────────────────────────────────────────────────


def test_haversine_zero_distance():
    assert _haversine_nm((50.0, 1.0), (50.0, 1.0)) < 0.001


def test_haversine_known_pair():
    # Casablanca -> Felixstowe is ~1170 nm great-circle (independently verified).
    # Bounds are wide enough to absorb any rounding without giving up sanity.
    casablanca = (33.6066, -7.6182)
    felixstowe = (51.954, 1.35)
    distance = _haversine_nm(casablanca, felixstowe)
    assert 1100 < distance < 1250


# ── Port lookup ───────────────────────────────────────────────────────────────


def test_port_coords_known_ports():
    assert _port_coords("GBSOU") is not None
    assert _port_coords("MACAS") is not None


def test_port_coords_case_insensitive():
    assert _port_coords("gbsou") == _port_coords("GBSOU")
    assert _port_coords(" GBSOU ") == _port_coords("GBSOU")


def test_port_coords_unknown_returns_none():
    assert _port_coords("XXXXX") is None
    assert _port_coords(None) is None
    assert _port_coords("") is None


# ── Hour comparisons ──────────────────────────────────────────────────────────


def test_hours_between_naive_datetimes_are_treated_as_utc():
    a = datetime(2026, 4, 30, 10, 0, 0)  # naive
    b = datetime(2026, 4, 30, 13, 30, 0)  # naive
    assert abs(_hours_between(a, b) - 3.5) < 1e-6


def test_hours_between_is_symmetric():
    a = datetime(2026, 4, 30, 10, 0, 0, tzinfo=UTC)
    b = datetime(2026, 4, 30, 13, 0, 0, tzinfo=UTC)
    assert _hours_between(a, b) == _hours_between(b, a)


def test_signed_hours_after():
    earlier = datetime(2026, 4, 30, 10, 0, 0, tzinfo=UTC)
    later = datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC)
    assert _signed_hours_after(later, earlier) == 6.0
    assert _signed_hours_after(earlier, later) == -6.0


# ── derive_status ─────────────────────────────────────────────────────────────


def _pos(
    *,
    lat: float | None = None,
    lon: float | None = None,
    navstat: int | None = 0,
    eta: datetime | None = None,
) -> FleetVesselPosition:
    return FleetVesselPosition(
        imo="9321483",
        mmsi=304491000,
        timestamp=None,
        latitude=lat,
        longitude=lon,
        course=None,
        speed=None,
        heading=None,
        navstat=navstat,
        eta=eta,
        destination=None,
    )


_SOUTHAMPTON = (50.9097, -1.4044)


def test_derive_status_arrived_when_stationary_near_port():
    position = _pos(lat=_SOUTHAMPTON[0], lon=_SOUTHAMPTON[1], navstat=5)
    status = derive_status(
        position=position,
        discharge_port_code="GBSOU",
        stored_eta=None,
        approaching_radius_nm=50.0,
        delayed_threshold_hours=24.0,
    )
    assert status == VesselUpdateStatus.ARRIVED


def test_derive_status_approaching_when_underway_near_port():
    # 30 nm offshore from Southampton, NAVSTAT 0 (under way using engine)
    position = _pos(lat=_SOUTHAMPTON[0] + 0.5, lon=_SOUTHAMPTON[1], navstat=0)
    status = derive_status(
        position=position,
        discharge_port_code="GBSOU",
        stored_eta=None,
        approaching_radius_nm=50.0,
        delayed_threshold_hours=24.0,
    )
    assert status == VesselUpdateStatus.APPROACHING


def test_derive_status_delayed_when_eta_slips_past_threshold():
    # Far from port, ETA pushed by 36h vs stored
    stored = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    revised = stored + timedelta(hours=36)
    position = _pos(lat=0.0, lon=0.0, navstat=0, eta=revised)
    status = derive_status(
        position=position,
        discharge_port_code="GBSOU",
        stored_eta=stored,
        approaching_radius_nm=50.0,
        delayed_threshold_hours=24.0,
    )
    assert status == VesselUpdateStatus.DELAYED


def test_derive_status_in_transit_when_eta_slip_below_threshold():
    stored = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    revised = stored + timedelta(hours=12)  # < 24h threshold
    position = _pos(lat=0.0, lon=0.0, navstat=0, eta=revised)
    status = derive_status(
        position=position,
        discharge_port_code="GBSOU",
        stored_eta=stored,
        approaching_radius_nm=50.0,
        delayed_threshold_hours=24.0,
    )
    assert status == VesselUpdateStatus.IN_TRANSIT


def test_derive_status_default_in_transit_when_far_from_port_no_eta():
    position = _pos(lat=0.0, lon=0.0, navstat=0, eta=None)
    status = derive_status(
        position=position,
        discharge_port_code="GBSOU",
        stored_eta=None,
        approaching_radius_nm=50.0,
        delayed_threshold_hours=24.0,
    )
    assert status == VesselUpdateStatus.IN_TRANSIT


def test_derive_status_unknown_port_falls_through_to_in_transit():
    """Unknown discharge port → no port-radius check possible. Should not raise."""
    position = _pos(lat=50.9, lon=-1.4, navstat=5)
    status = derive_status(
        position=position,
        discharge_port_code="XXUNK",
        stored_eta=None,
        approaching_radius_nm=50.0,
        delayed_threshold_hours=24.0,
    )
    assert status == VesselUpdateStatus.IN_TRANSIT


def test_derive_status_arrived_takes_precedence_over_delayed():
    """If a vessel is moored at port AND its ETA slipped — that's ARRIVED, not DELAYED."""
    stored = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    revised = stored + timedelta(hours=48)
    position = _pos(lat=_SOUTHAMPTON[0], lon=_SOUTHAMPTON[1], navstat=5, eta=revised)
    status = derive_status(
        position=position,
        discharge_port_code="GBSOU",
        stored_eta=stored,
        approaching_radius_nm=50.0,
        delayed_threshold_hours=24.0,
    )
    assert status == VesselUpdateStatus.ARRIVED


# ── _position_note ────────────────────────────────────────────────────────────


def test_position_note_compact_format():
    position = _pos(lat=51.954, lon=1.35, navstat=0)
    # _position_note isn't exported — reach into the module.
    note = vps._position_note(position)
    assert note is not None
    assert "lat=51.9540" in note
    assert "lon=1.3500" in note
    assert "navstat=0" in note


def test_position_note_returns_none_when_no_data():
    position = _pos(lat=None, lon=None, navstat=None)
    assert vps._position_note(position) is None
