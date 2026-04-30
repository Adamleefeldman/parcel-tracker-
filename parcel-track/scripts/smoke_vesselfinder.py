#!/usr/bin/env python3
"""Smoke test for VesselFinder /vesselslist round-trip.

Reads `VESSELFINDER_FLEET_KEY` + `VESSELFINDER_BASE_URL` from `.env`, makes
one real call to the fleet endpoint, and prints a one-line summary per
vessel returned. No DB writes, no notifications, no beat scheduling — pure
connectivity check.

Use this to validate the API key + fleet membership BEFORE flipping
`VESSELFINDER_ENABLED=true` in production.

Usage:

    uv run python scripts/smoke_vesselfinder.py

Exits 0 on success, 1 on any failure (HTTP error, auth error, or empty
fleet — an empty fleet is treated as a soft failure because it usually
means ops forgot to add vessels via the VF dashboard).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make `app` importable when this script is run directly with `uv run …`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations._exceptions import IntegrationError
from app.integrations.vesselfinder import VesselFinderClient


async def _round_trip() -> int:
    client = VesselFinderClient()
    positions = await client.get_fleet_positions()

    if not positions:
        print(
            "WARN — fleet endpoint returned 0 vessels. "
            "Add vessels via the VesselFinder dashboard before enabling the poller.",
            file=sys.stderr,
        )
        return 1

    print(f"OK — VesselFinder returned {len(positions)} vessel(s):")
    for p in positions:
        eta = p.eta.isoformat() if p.eta else "—"
        ts = p.timestamp.isoformat() if p.timestamp else "—"
        lat = f"{p.latitude:.4f}" if p.latitude is not None else "—"
        lon = f"{p.longitude:.4f}" if p.longitude is not None else "—"
        print(
            f"  imo={p.imo} mmsi={p.mmsi} navstat={p.navstat} "
            f"pos=({lat},{lon}) eta={eta} dest={p.destination or '—'} ts={ts}"
        )
    return 0


def main() -> int:
    try:
        return asyncio.run(_round_trip())
    except IntegrationError as exc:
        print(f"FAIL — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FAIL — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
