"""Money-risk dashboard schemas (mobile Phase 10).

Read-only aggregations over data already in the DB — no new columns. Three
sections power the mobile "Alerts" / Money-risk tab:

  * A/R aging   — full sale-value exposure of delivered-but-unbanked containers,
                  bucketed by how long they have sat unpaid.
  * Demurrage   — free-time countdown per arrived container.
  * Disputes    — acknowledged vs unacknowledged counts.

All money fields are ``Decimal``; under ``response_model`` Pydantic serialises
them to JSON **strings**, which the mobile money helpers depend on.
"""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.core.enums import ContainerLifecycleStatus, UKPort

# ── A/R aging ──────────────────────────────────────────────────────────────────


class ARAgingBucket(BaseModel):
    """One aging band. ``label`` is the day range; ``amount`` sums
    ``sale_price_total`` of the containers in the band (NULL prices count as 0)."""

    label: str  # "0-14" | "15-30" | "31-60" | "60+"
    count: int
    amount: Decimal


class AgedContainerOut(BaseModel):
    """A single delivered-but-unbanked container.

    ``days_aged`` is measured from ``Container.updated_at`` — the same proxy the
    A/R alerter uses (a precise ``delivered_at`` is deferred per ROADMAP), so the
    age is approximate.
    """

    container_id: uuid.UUID
    container_number: str
    booking_id: uuid.UUID
    lifecycle_status: ContainerLifecycleStatus
    sale_price_total: Decimal | None = None
    days_aged: int


class ARAgingSummary(BaseModel):
    """Total outstanding GBP exposure across unbanked containers, bucketed.

    ``total_outstanding`` is the **full** sale value of unbanked containers — it
    is not netted against any already-banked tranche (full exposure view). The
    ``containers`` list is capped (see ``containers_truncated``); use the
    drill-in endpoint for the complete list once one exists.
    """

    total_outstanding: Decimal
    container_count: int
    buckets: list[ARAgingBucket]
    containers: list[AgedContainerOut]
    containers_truncated: bool


# ── Demurrage countdown ─────────────────────────────────────────────────────────


class DemurrageCountdownOut(BaseModel):
    """Free-demurrage-time countdown for one arrived container.

    ``Vessel.ata`` is a ``date`` (no time component), so the honest precision is
    whole days: ``days_remaining`` is an integer and goes negative once free time
    has expired. No hour-level precision is fabricated.
    """

    booking_id: uuid.UUID
    container_id: uuid.UUID
    container_number: str
    port_of_discharge: UKPort | None = None
    ata: date
    free_days: int
    days_remaining: int
    expired: bool
    rate_gbp_after: Decimal | None = None


class DemurrageSummary(BaseModel):
    """Per-container demurrage countdowns, soonest-expiring first.

    ``expiring_count`` counts rows with ``days_remaining <=
    DEMURRAGE_WARNING_LEAD_DAYS`` (includes already-expired rows).
    """

    expiring_count: int
    soonest_days_remaining: int | None = None
    items: list[DemurrageCountdownOut]


# ── Disputes ────────────────────────────────────────────────────────────────────


class DisputeSummary(BaseModel):
    unacknowledged_count: int
    acknowledged_count: int


# ── Combined ────────────────────────────────────────────────────────────────────


class MoneyRiskOut(BaseModel):
    ar_aging: ARAgingSummary
    demurrage: DemurrageSummary
    disputes: DisputeSummary
