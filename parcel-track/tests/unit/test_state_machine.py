"""Unit tests for the state-machine data and financial masking in shipment_service."""

from __future__ import annotations

from app.core.enums import ShipmentStatus
from app.services.shipment_service import VALID_TRANSITIONS, ShipmentService

# ── VALID_TRANSITIONS ─────────────────────────────────────────────────────────

_FORWARD_CHAIN = [
    ShipmentStatus.DRAFT,
    ShipmentStatus.PO_SUBMITTED,
    ShipmentStatus.INVOICE_RECEIVED,
    ShipmentStatus.PAYMENT_CONFIRMED,
    ShipmentStatus.BL_ISSUED,
    ShipmentStatus.IN_TRANSIT,
    ShipmentStatus.CLEARED,
    ShipmentStatus.COMPLETE,
]


def test_every_status_has_an_entry():
    for s in ShipmentStatus:
        assert s in VALID_TRANSITIONS, f"{s!r} missing from VALID_TRANSITIONS"


def test_complete_is_terminal():
    assert VALID_TRANSITIONS[ShipmentStatus.COMPLETE] == []


def test_forward_chain_is_traversable():
    for i in range(len(_FORWARD_CHAIN) - 1):
        current = _FORWARD_CHAIN[i]
        next_state = _FORWARD_CHAIN[i + 1]
        assert next_state in VALID_TRANSITIONS[current], (
            f"{next_state!r} not reachable from {current!r}"
        )


def test_no_backward_transitions():
    for i, state in enumerate(_FORWARD_CHAIN):
        allowed = VALID_TRANSITIONS[state]
        for earlier in _FORWARD_CHAIN[:i]:
            assert earlier not in allowed, (
                f"backward transition {state!r} → {earlier!r} should not exist"
            )


def test_no_skip_transitions():
    for i, state in enumerate(_FORWARD_CHAIN[:-2]):
        allowed = VALID_TRANSITIONS[state]
        for skipped in _FORWARD_CHAIN[i + 2 :]:
            assert skipped not in allowed, (
                f"skip transition {state!r} → {skipped!r} should not exist"
            )


# ── mask_financials ───────────────────────────────────────────────────────────

_FINANCIAL_KEYS = {"total_value", "value", "amount", "swift_ref", "duty_paid", "estimated_duty_vat"}
_SAFE_KEYS = {"reference", "status", "id"}

_SAMPLE = {
    "reference": "SHP-001",
    "status": "draft",
    "id": "abc-123",
    "total_value": "10000.00",
    "value": "10000.00",
    "amount": "5000.00",
    "swift_ref": "SW-XYZ",
    "duty_paid": "200.00",
    "estimated_duty_vat": "300.00",
}


def test_mask_financials_show_true_returns_unchanged():
    result = ShipmentService.mask_financials(_SAMPLE.copy(), show=True)
    assert result == _SAMPLE


def test_mask_financials_show_false_nulls_financial_keys():
    result = ShipmentService.mask_financials(_SAMPLE.copy(), show=False)
    for key in _FINANCIAL_KEYS:
        assert result[key] is None, f"expected {key!r} to be None"


def test_mask_financials_show_false_preserves_safe_keys():
    result = ShipmentService.mask_financials(_SAMPLE.copy(), show=False)
    for key in _SAFE_KEYS:
        assert result[key] == _SAMPLE[key], f"expected {key!r} to be unchanged"


def test_mask_financials_non_financial_obj_unaffected():
    obj = {"reference": "X", "status": "draft"}
    assert ShipmentService.mask_financials(obj, show=False) == obj


def test_mask_financials_empty_dict():
    assert ShipmentService.mask_financials({}, show=False) == {}
    assert ShipmentService.mask_financials({}, show=True) == {}
