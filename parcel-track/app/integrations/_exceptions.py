"""Typed exceptions raised by the integrations layer.

Callers catch these instead of `httpx.*` errors so the request layer does not
leak into service / task code. `send_push_notification` relies on the
`IntegrationTimeout` / `IntegrationUnavailable` distinction for Celery
`autoretry_for` — do not collapse them into a single class.
"""

from __future__ import annotations


class IntegrationError(Exception):
    """Base class for any failure talking to an external provider."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class IntegrationTimeout(IntegrationError):
    """Request exceeded the configured timeout (connect, read, or total)."""


class IntegrationUnavailable(IntegrationError):
    """Provider returned 5xx or the circuit breaker is open."""


class IntegrationRateLimited(IntegrationError):
    """Provider returned 429. `retry_after_seconds` reflects the `Retry-After` header if present."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider)
        self.retry_after_seconds = retry_after_seconds


class IntegrationAuthError(IntegrationError):
    """Provider returned 401/403 — credentials are wrong or lack scope."""
