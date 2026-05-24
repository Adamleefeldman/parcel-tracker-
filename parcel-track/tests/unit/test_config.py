"""
Unit tests for Settings parsers and the production boot-time validator.

Covers the ALLOWED_HOSTS / CORS comma-list parsing and the production
guard that refuses to boot when either list is empty.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings

# Minimal valid production settings — every individual test fills in or
# overrides the field it's actually exercising. SECRET_KEY is 64 hex chars
# (>= 32 required) and not on the placeholder list.
_VALID_PROD_KWARGS: dict[str, str] = {
    "APP_ENV": "production",
    "SECRET_KEY": "a" * 64,
    "DATABASE_URL": "postgresql+asyncpg://u:p@h/d",
    "DATABASE_URL_SYNC": "postgresql://u:p@h/d",
    "STORAGE_BUCKET": "bucket",
    "STORAGE_ENDPOINT_URL": "https://example.r2.cloudflarestorage.com",
    "STORAGE_ACCESS_KEY_ID": "key",
    "STORAGE_SECRET_ACCESS_KEY": "secret",
    "STORAGE_PUBLIC_URL": "https://files.example.com",
    "REDIS_URL": "redis://prod-redis:6379/0",
    "CORS_ALLOWED_ORIGINS": "https://app.example.com",
    "ALLOWED_HOSTS": "api.example.com",
}


# ── allowed_hosts parsing ─────────────────────────────────────────────────────


def test_allowed_hosts_parses_comma_separated_list():
    s = Settings(**{**_VALID_PROD_KWARGS, "ALLOWED_HOSTS": "a.com,b.com,c.com"})  # type: ignore[arg-type]
    assert s.allowed_hosts == ["a.com", "b.com", "c.com"]


def test_allowed_hosts_strips_whitespace_and_drops_empties():
    s = Settings(  # type: ignore[arg-type]
        **{**_VALID_PROD_KWARGS, "ALLOWED_HOSTS": "  a.com , ,b.com,  "}
    )
    assert s.allowed_hosts == ["a.com", "b.com"]


def test_allowed_hosts_empty_string_yields_empty_list():
    # Use dev env so the production validator doesn't fire on the empty value.
    s = Settings(  # type: ignore[arg-type]
        **{**_VALID_PROD_KWARGS, "APP_ENV": "development", "ALLOWED_HOSTS": ""}
    )
    assert s.allowed_hosts == []


# ── production validator ──────────────────────────────────────────────────────


def test_production_rejects_empty_allowed_hosts():
    with pytest.raises(ValueError, match="ALLOWED_HOSTS must be set in production"):
        Settings(**{**_VALID_PROD_KWARGS, "ALLOWED_HOSTS": ""})  # type: ignore[arg-type]


def test_production_accepts_non_empty_allowed_hosts():
    # Sanity check: the validator passes when ALLOWED_HOSTS is populated, so
    # the rejection above is specifically about emptiness, not an unrelated
    # validation failure in the fixture.
    s = Settings(**_VALID_PROD_KWARGS)  # type: ignore[arg-type]
    assert s.allowed_hosts == ["api.example.com"]
