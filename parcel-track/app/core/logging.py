"""
Structured logging configuration for ParcelTrack.

JSON output in production, human-readable in development.
A request_id context variable is set per-request by the request logging
middleware and automatically included in every log record.
"""

from __future__ import annotations

import logging
import logging.config
from contextvars import ContextVar

from app.core.config import get_settings

# Per-request correlation ID — set by RequestLoggingMiddleware.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class _RequestIdFilter(logging.Filter):
    """Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()  # type: ignore[attr-defined]
        return True


def setup_logging() -> None:
    settings = get_settings()
    level = settings.LOG_LEVEL.upper()

    if settings.is_production:
        formatter_cfg = {
            "class": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        }
    else:
        formatter_cfg = {
            "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s (rid=%(request_id)s)",
            "datefmt": "%H:%M:%S",
        }

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {
                "()": _RequestIdFilter,
            },
        },
        "formatters": {
            "default": formatter_cfg,
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "filters": ["request_id"],
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "parceltrack": {
                "level": level,
                "handlers": ["console"],
                "propagate": False,
            },
            # Quiet noisy libraries in production
            "uvicorn.access": {
                "level": "WARNING" if settings.is_production else level,
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)
