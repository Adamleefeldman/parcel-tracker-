"""
Network utility — shared client IP resolution.

Used by both the rate limiter and the audit log so that X-Forwarded-For
is only trusted when all three conditions hold:
  1. APP_ENV == "production"
  2. TRUSTED_PROXIES is set (comma-separated IPs or CIDRs)
  3. The direct peer IP matches one of those trusted proxies

In all other cases the direct socket peer is used, preventing XFF spoofing.
"""

from __future__ import annotations

import ipaddress
import logging

from fastapi import Request

logger = logging.getLogger("parceltrack.api")


def _parse_trusted_proxies(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("Skipping malformed trusted proxy entry: %s", entry)
    return networks


def get_client_ip(request: Request, is_production: bool, trusted_proxies: str) -> str | None:
    """
    Resolve the real client IP for a request.

    Honours X-Forwarded-For only in production when the direct peer is a
    configured trusted proxy. Otherwise returns the direct socket peer IP.
    """
    peer_ip = request.client.host if request.client else None

    if is_production and trusted_proxies and peer_ip:
        trusted = _parse_trusted_proxies(trusted_proxies)
        try:
            peer = ipaddress.ip_address(peer_ip)
        except ValueError:
            return peer_ip

        if any(peer in network for network in trusted):
            xff = request.headers.get("X-Forwarded-For", "")
            if xff:
                return xff.split(",")[0].strip()

    return peer_ip
