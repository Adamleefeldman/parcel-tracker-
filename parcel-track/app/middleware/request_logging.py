"""
Request logging middleware.

Logs every HTTP request with method, path, status code, and duration.
Generates a UUID4 request_id per request and attaches it to:
  - The response as an X-Request-ID header
  - A contextvars.ContextVar so downstream loggers auto-include it
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

logger = logging.getLogger("parceltrack.api")

# Paths excluded from request logging to avoid health-check noise.
_SKIP_PATHS = frozenset({"/health", "/ready"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        rid = uuid.uuid4().hex
        request_id_ctx.set(rid)

        client_ip = request.client.host if request.client else "unknown"
        start = time.perf_counter()

        response: Response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid

        log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
        if response.status_code >= 500:
            log_level = logging.ERROR

        logger.log(
            log_level,
            "%s %s %d %.1fms ip=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            client_ip,
        )

        return response
