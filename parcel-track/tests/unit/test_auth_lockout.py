"""
Unit tests for the login lockout helpers in app.core.redis and the lockout
logic wired into AuthService.login().

All Redis calls are replaced with an in-process fake so no real Redis is needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.enums import UserRole
from app.core.redis import (
    clear_login_failures,
    get_lockout_ttl,
    increment_login_failure,
    is_login_locked,
)
from app.schemas.schemas import LoginRequest
from app.services.auth_service import AuthService

# ── increment_login_failure ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_increment_sets_expire_on_first_call():
    """TTL must be set on the first increment (count == 1) to fix the window start."""
    redis = MagicMock()
    expire_calls: list[tuple] = []

    async def fake_incr(key):
        return 1

    async def fake_expire(key, secs):
        expire_calls.append((key, secs))

    redis.incr = fake_incr
    redis.expire = fake_expire

    with patch("app.core.redis.get_redis_client", return_value=redis):
        count = await increment_login_failure("user@example.com", 900)

    assert count == 1
    assert len(expire_calls) == 1
    assert expire_calls[0] == ("auth:lockout:user@example.com", 900)


@pytest.mark.asyncio
async def test_increment_does_not_reset_expire_on_subsequent_calls():
    """expire() must only be called when count == 1, not on every failure."""
    redis = MagicMock()
    call_count = 0
    expire_calls: list = []

    async def fake_incr(key):
        nonlocal call_count
        call_count += 1
        return call_count

    async def fake_expire(key, secs):
        expire_calls.append(secs)

    redis.incr = fake_incr
    redis.expire = fake_expire

    with patch("app.core.redis.get_redis_client", return_value=redis):
        await increment_login_failure("user@example.com", 900)
        await increment_login_failure("user@example.com", 900)
        await increment_login_failure("user@example.com", 900)

    assert len(expire_calls) == 1  # only the first call sets TTL


# ── is_login_locked ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_not_locked_below_threshold():
    redis = MagicMock()
    redis.get = AsyncMock(return_value="3")

    with patch("app.core.redis.get_redis_client", return_value=redis):
        assert await is_login_locked("user@example.com", threshold=5) is False


@pytest.mark.asyncio
async def test_locked_at_threshold():
    redis = MagicMock()
    redis.get = AsyncMock(return_value="5")

    with patch("app.core.redis.get_redis_client", return_value=redis):
        assert await is_login_locked("user@example.com", threshold=5) is True


@pytest.mark.asyncio
async def test_locked_above_threshold():
    redis = MagicMock()
    redis.get = AsyncMock(return_value="9")

    with patch("app.core.redis.get_redis_client", return_value=redis):
        assert await is_login_locked("user@example.com", threshold=5) is True


@pytest.mark.asyncio
async def test_not_locked_when_key_absent():
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)

    with patch("app.core.redis.get_redis_client", return_value=redis):
        assert await is_login_locked("user@example.com", threshold=5) is False


# ── get_lockout_ttl ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lockout_ttl_returns_remaining_seconds():
    redis = MagicMock()
    redis.ttl = AsyncMock(return_value=742)

    with patch("app.core.redis.get_redis_client", return_value=redis):
        assert await get_lockout_ttl("user@example.com") == 742


@pytest.mark.asyncio
async def test_get_lockout_ttl_clamps_negative_to_zero():
    redis = MagicMock()
    redis.ttl = AsyncMock(return_value=-2)  # key doesn't exist

    with patch("app.core.redis.get_redis_client", return_value=redis):
        assert await get_lockout_ttl("user@example.com") == 0


# ── clear_login_failures ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_deletes_key():
    redis = MagicMock()
    deleted: list[str] = []

    async def fake_delete(key):
        deleted.append(key)

    redis.delete = fake_delete

    with patch("app.core.redis.get_redis_client", return_value=redis):
        await clear_login_failures("user@example.com")

    assert deleted == ["auth:lockout:user@example.com"]


# ── AuthService.login() integration ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_raises_429_when_already_locked():
    """Account that is already locked should be rejected before any DB call."""
    with (
        patch("app.services.auth_service.is_login_locked", AsyncMock(return_value=True)),
        patch("app.services.auth_service.get_lockout_ttl", AsyncMock(return_value=600)),
    ):
        db = AsyncMock()
        request = LoginRequest(email="locked@example.com", password="anything")

        with pytest.raises(HTTPException) as exc_info:
            await AuthService.login(db, request)

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        assert exc_info.value.headers["Retry-After"] == "600"


@pytest.mark.asyncio
async def test_login_raises_429_on_threshold_crossing_failure():
    """The 5th failure (hitting the threshold) should return 429, not 401."""
    no_user = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    with (
        patch("app.services.auth_service.is_login_locked", AsyncMock(return_value=False)),
        patch("app.services.auth_service.increment_login_failure", AsyncMock(return_value=5)),
        patch("app.services.auth_service.get_lockout_ttl", AsyncMock(return_value=900)),
    ):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=no_user)
        request = LoginRequest(email="user@example.com", password="wrongpass")

        with pytest.raises(HTTPException) as exc_info:
            await AuthService.login(db, request)

        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_login_raises_401_before_threshold():
    """Failures below the threshold return 401, not 429."""
    no_user = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    with (
        patch("app.services.auth_service.is_login_locked", AsyncMock(return_value=False)),
        patch("app.services.auth_service.increment_login_failure", AsyncMock(return_value=2)),
        patch("app.services.auth_service.get_lockout_ttl", AsyncMock(return_value=870)),
    ):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=no_user)
        request = LoginRequest(email="user@example.com", password="wrongpass")

        with pytest.raises(HTTPException) as exc_info:
            await AuthService.login(db, request)

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_user_with_null_hashed_password_returns_401():
    """A user record with no hashed_password (nullable column) must not crash
    verify_password — they get a clean 401 like any other failed credential."""
    user_no_pwd = MagicMock()
    user_no_pwd.hashed_password = None
    no_pwd_result = MagicMock(scalar_one_or_none=MagicMock(return_value=user_no_pwd))

    with (
        patch("app.services.auth_service.is_login_locked", AsyncMock(return_value=False)),
        patch("app.services.auth_service.increment_login_failure", AsyncMock(return_value=1)),
        patch("app.services.auth_service.get_lockout_ttl", AsyncMock(return_value=900)),
        # If verify_password ever runs with None, it explodes; the narrowing
        # in AuthService.login should short-circuit before reaching it.
        patch(
            "app.services.auth_service.verify_password",
            side_effect=AssertionError("verify_password should not be called with None"),
        ),
    ):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=no_pwd_result)
        request = LoginRequest(email="nopwd@example.com", password="anything")

        with pytest.raises(HTTPException) as exc_info:
            await AuthService.login(db, request)

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_successful_login_clears_failure_counter():
    """A successful login must reset the failure counter."""
    mock_user = MagicMock()
    mock_user.id = "abc123"
    mock_user.role = UserRole.ADMIN
    mock_user.hashed_password = "hashed"

    clear_mock = AsyncMock()

    with (
        patch("app.services.auth_service.is_login_locked", AsyncMock(return_value=False)),
        patch("app.services.auth_service.clear_login_failures", clear_mock),
        patch("app.services.auth_service.verify_password", return_value=True),
        patch("app.services.auth_service.create_access_token", return_value="access_tok"),
        patch("app.services.auth_service.create_refresh_token", return_value=("raw", "hashed")),
        patch("app.services.auth_service.refresh_token_expiry", return_value=None),
    ):
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        db.add = MagicMock()

        request = LoginRequest(email="user@example.com", password="correctpass")
        result = await AuthService.login(db, request)

    clear_mock.assert_awaited_once_with("user@example.com")
    assert result["access_token"] == "access_tok"
