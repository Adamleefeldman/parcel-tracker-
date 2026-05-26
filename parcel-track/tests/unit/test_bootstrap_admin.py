"""
Unit tests for the docker/host DATABASE_URL mismatch guard in
``scripts/bootstrap_admin.py``.

The trap the guard exists to prevent: the host explicitly loads
``.env.supabase`` (or otherwise points at a different DB than the local
compose stack) while the ``parceltrack-api`` container is still hitting
compose-local Postgres. Seeding from the host then succeeds against the
wrong DB, the local API still sees an empty users table, and login
returns 401 with no obvious clue.

The equality check compares ``(port, dbname)`` so the host-side URL
(``localhost:5432/parceltrack``) is treated as the same database as
the compose-internal URL (``postgres:5432/parceltrack``) — they refer
to the same Postgres service via different network paths.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from scripts.bootstrap_admin import _db_identity, _db_target, _detect_db_mismatch

_HOST_SUPABASE = "postgresql+asyncpg://u:p@aws-1-eu-west-2.pooler.supabase.com:5432/postgres"
_COMPOSE_LOCAL = "postgresql+asyncpg://u:p@postgres:5432/parceltrack"
_HOST_LOCAL = "postgresql+asyncpg://u:p@localhost:5432/parceltrack"


def _ps_result(names: str, returncode: int = 0) -> MagicMock:
    res = MagicMock(spec=subprocess.CompletedProcess)
    res.returncode = returncode
    res.stdout = names
    return res


def _exec_result(value: str, returncode: int = 0) -> MagicMock:
    res = MagicMock(spec=subprocess.CompletedProcess)
    res.returncode = returncode
    res.stdout = value
    return res


@pytest.fixture
def mock_run() -> Iterator[MagicMock]:
    with patch("scripts.bootstrap_admin.subprocess.run") as m:
        yield m


def test_db_target_renders_host_port_dbname_for_diagnostics() -> None:
    """``_db_target`` is for human-readable display; equality uses ``_db_identity``."""
    assert _db_target(_HOST_SUPABASE) == "aws-1-eu-west-2.pooler.supabase.com:5432/postgres"
    assert _db_target(_COMPOSE_LOCAL) == "postgres:5432/parceltrack"
    assert _db_target(_HOST_LOCAL) == "localhost:5432/parceltrack"


def test_db_target_defaults_port_when_omitted() -> None:
    assert _db_target("postgresql://u:p@db/x") == "db:5432/x"


def test_db_identity_treats_localhost_and_compose_hostname_as_same() -> None:
    """Host ``.env`` (localhost) and compose container (`postgres`) target the SAME DB."""
    assert _db_identity(_HOST_LOCAL) == _db_identity(_COMPOSE_LOCAL)


def test_db_identity_separates_supabase_from_local() -> None:
    """Different dbname → different identity → safeguard fires correctly."""
    assert _db_identity(_HOST_SUPABASE) != _db_identity(_COMPOSE_LOCAL)


def test_returns_none_when_docker_not_installed(mock_run: MagicMock) -> None:
    mock_run.side_effect = FileNotFoundError("docker not on PATH")
    assert _detect_db_mismatch(_HOST_SUPABASE) is None


def test_returns_none_when_docker_ps_times_out(mock_run: MagicMock) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker ps", timeout=2.0)
    assert _detect_db_mismatch(_HOST_SUPABASE) is None


def test_returns_none_when_docker_ps_fails(mock_run: MagicMock) -> None:
    mock_run.return_value = _ps_result("", returncode=1)
    assert _detect_db_mismatch(_HOST_SUPABASE) is None


def test_returns_none_when_api_container_not_running(mock_run: MagicMock) -> None:
    mock_run.return_value = _ps_result("parceltrack-postgres\nparceltrack-redis\n")
    assert _detect_db_mismatch(_HOST_SUPABASE) is None
    # Only one call — we short-circuit before docker exec.
    assert mock_run.call_count == 1


def test_returns_none_when_docker_exec_fails(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        _ps_result("parceltrack-api\nparceltrack-postgres\n"),
        _exec_result("", returncode=1),
    ]
    assert _detect_db_mismatch(_HOST_SUPABASE) is None


def test_returns_none_when_container_env_empty(mock_run: MagicMock) -> None:
    """A blank ``DATABASE_URL`` in the container is treated as 'no info' rather than mismatch."""
    mock_run.side_effect = [
        _ps_result("parceltrack-api\n"),
        _exec_result(""),
    ]
    assert _detect_db_mismatch(_HOST_SUPABASE) is None


def test_returns_none_when_urls_match(mock_run: MagicMock) -> None:
    """Host .env (localhost) and compose container (`postgres`) → same DB, no warning."""
    mock_run.side_effect = [
        _ps_result("parceltrack-api\n"),
        _exec_result(_COMPOSE_LOCAL + "\n"),
    ]
    assert _detect_db_mismatch(_HOST_LOCAL) is None


def test_returns_mismatch_tuple_when_targets_differ(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        _ps_result("parceltrack-api\nparceltrack-postgres\nparceltrack-redis\n"),
        _exec_result(_COMPOSE_LOCAL + "\n"),
    ]
    result = _detect_db_mismatch(_HOST_SUPABASE)
    assert result == (_HOST_SUPABASE, _COMPOSE_LOCAL)


def test_probe_uses_short_timeout(mock_run: MagicMock) -> None:
    """A hung docker daemon must not freeze the bootstrap script indefinitely."""
    mock_run.side_effect = [
        _ps_result("parceltrack-api\n"),
        _exec_result(_COMPOSE_LOCAL),
    ]
    _detect_db_mismatch(_HOST_SUPABASE)
    for call in mock_run.call_args_list:
        kwargs: dict[str, Any] = call.kwargs
        assert kwargs.get("timeout") is not None and kwargs["timeout"] <= 5.0
