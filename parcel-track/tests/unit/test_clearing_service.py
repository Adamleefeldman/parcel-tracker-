"""Unit tests for ClearingService pure helpers."""

from __future__ import annotations

import pytest

from app.core.enums import ClearingDocsStatus
from app.services.clearing_service import ClearingService

# ── _derive_status truth table ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "customs,packing,cert,expected",
    [
        (False, False, False, None),  # none set → no status change
        (True, False, False, ClearingDocsStatus.PARTIAL),
        (False, True, False, ClearingDocsStatus.PARTIAL),
        (False, False, True, ClearingDocsStatus.PARTIAL),
        (True, True, False, ClearingDocsStatus.PARTIAL),
        (True, False, True, ClearingDocsStatus.PARTIAL),
        (False, True, True, ClearingDocsStatus.PARTIAL),
        (True, True, True, ClearingDocsStatus.COMPLETE),  # all set → complete
    ],
)
def test_derive_status(customs, packing, cert, expected):
    result = ClearingService._derive_status(customs, packing, cert)
    assert result == expected
