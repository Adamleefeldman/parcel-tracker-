"""Unit tests for app/core/security.py — all pure functions, no DB or network."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from app.core.enums import UserRole
from app.core.security import (
    create_access_token,
    create_invite_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_token,
    invite_token_expiry,
    refresh_token_expiry,
    verify_password,
)

# ── hash_password / verify_password ──────────────────────────────────────────


def test_verify_password_round_trip(monkeypatch):
    monkeypatch.setattr("app.core.security.pwd_context.hash", lambda p: f"hashed:{p}")
    monkeypatch.setattr(
        "app.core.security.pwd_context.verify", lambda plain, hashed: hashed == f"hashed:{plain}"
    )

    hashed = hash_password("mysecret")
    assert verify_password("mysecret", hashed) is True


def test_verify_password_wrong_password(monkeypatch):
    monkeypatch.setattr("app.core.security.pwd_context.hash", lambda p: f"hashed:{p}")
    monkeypatch.setattr(
        "app.core.security.pwd_context.verify", lambda plain, hashed: hashed == f"hashed:{plain}"
    )

    hashed = hash_password("mysecret")
    assert verify_password("wrongpassword", hashed) is False


# ── create_access_token / decode_access_token ─────────────────────────────────


def test_access_token_round_trip():
    token = create_access_token("user-123", UserRole.ADMIN)
    payload = decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["role"] == UserRole.ADMIN.value
    assert payload["type"] == "access"
    assert "jti" in payload


def test_decode_access_token_wrong_secret(monkeypatch):
    token = create_access_token("user-123", UserRole.ADMIN)

    monkeypatch.setattr("app.core.security.settings.SECRET_KEY", "wrong-secret")
    result = decode_access_token(token)
    assert result is None


def test_decode_access_token_rejects_non_access_type():
    # Craft a token with type != "access" manually
    from jose import jwt

    from app.core.config import get_settings

    s = get_settings()
    payload = {"sub": "user-123", "role": "admin", "type": "refresh", "exp": 9999999999}
    token = jwt.encode(payload, s.SECRET_KEY, algorithm=s.JWT_ALGORITHM)
    assert decode_access_token(token) is None


def test_decode_access_token_invalid_returns_none():
    assert decode_access_token("not.a.token") is None


# ── create_refresh_token ──────────────────────────────────────────────────────


def test_create_refresh_token_returns_two_strings():
    raw, hashed = create_refresh_token()
    assert isinstance(raw, str) and len(raw) > 0
    assert isinstance(hashed, str) and len(hashed) > 0


def test_create_refresh_token_raw_differs_from_hash():
    raw, hashed = create_refresh_token()
    assert raw != hashed


def test_create_refresh_token_hash_is_sha256_hex():
    raw, hashed = create_refresh_token()
    expected = hashlib.sha256(raw.encode()).hexdigest()
    assert hashed == expected


def test_create_refresh_token_unique_each_call():
    raw1, _ = create_refresh_token()
    raw2, _ = create_refresh_token()
    assert raw1 != raw2


# ── create_invite_token ───────────────────────────────────────────────────────


def test_create_invite_token_returns_two_strings():
    raw, hashed = create_invite_token()
    assert isinstance(raw, str) and len(raw) > 0
    assert isinstance(hashed, str) and len(hashed) > 0


def test_create_invite_token_hash_is_sha256_hex():
    raw, hashed = create_invite_token()
    assert hashed == hashlib.sha256(raw.encode()).hexdigest()


# ── hash_token ────────────────────────────────────────────────────────────────


def test_hash_token_is_deterministic():
    assert hash_token("abc") == hash_token("abc")


def test_hash_token_different_inputs_differ():
    assert hash_token("abc") != hash_token("xyz")


def test_hash_token_matches_sha256():
    assert hash_token("hello") == hashlib.sha256(b"hello").hexdigest()


# ── expiry helpers ────────────────────────────────────────────────────────────


def test_refresh_token_expiry_is_in_the_future():
    assert refresh_token_expiry() > datetime.now(UTC)


def test_invite_token_expiry_is_in_the_future():
    assert invite_token_expiry() > datetime.now(UTC)


# ── bcrypt rounds wiring ──────────────────────────────────────────────────────


def test_bcrypt_uses_configured_rounds():
    from app.core.config import get_settings
    from app.core.security import pwd_context

    rounds = get_settings().BCRYPT_ROUNDS
    h = pwd_context.hash("pw")
    # bcrypt format: $2b$<rounds>$<22-char-salt><31-char-hash>
    assert h.startswith(f"$2b${rounds:02d}$")


# ── ShipmentMembership protocol ──────────────────────────────────────────────


def test_admin_membership_satisfies_shipment_membership_protocol():
    from app.core.enums import UserRole
    from app.middleware.auth import ShipmentMembership, _AdminMembership

    m = _AdminMembership()
    assert isinstance(m, ShipmentMembership)
    assert m.effective_role is UserRole.ADMIN
