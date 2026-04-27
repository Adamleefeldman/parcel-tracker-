"""Unit tests for InvoiceService pure helpers."""

from __future__ import annotations

import pytest

from app.services.invoice_service import InvoiceService

# ── _variance_exceeded ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "invoice_val,po_val,expected",
    [
        (100.0, 100.0, False),  # exact match — no discrepancy
        (102.0, 100.0, False),  # exactly 2% over — boundary, no discrepancy
        (98.0, 100.0, False),  # exactly 2% under — boundary, no discrepancy
        (102.01, 100.0, True),  # just over 2% — discrepancy
        (97.99, 100.0, True),  # just under -2% — discrepancy
        (110.0, 100.0, True),  # 10% over — discrepancy
        (50.0, 100.0, True),  # 50% under — discrepancy
        (1000.0, 980.0, True),  # 2.04% — discrepancy
        (1000.0, 1020.0, False),  # ~1.96% — no discrepancy
    ],
)
def test_variance_exceeded(invoice_val, po_val, expected):
    assert InvoiceService._variance_exceeded(invoice_val, po_val) is expected
