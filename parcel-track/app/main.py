"""
Application entry point.
All routers registered here. Exception handlers provide consistent error shape.
"""

import asyncio
import logging

import sentry_sdk
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import (
    auth_router,
    bl_router,
    clearing_router,
    container_router,
    customs_router,
    delivery_router,
    doc_router,
    invoice_router,
    notif_router,
    payment_router,
    po_router,
    shipment_router,
    vessel_router,
)
from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.logging import setup_logging
from app.db.database import get_db
from app.middleware.auth import bearer_scheme, get_current_user
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

setup_logging()

settings = get_settings()
logger = logging.getLogger("parceltrack.api")

# Cap each /ready dependency probe so a stuck Postgres or Redis connection
# can't hang the readiness endpoint until the load balancer's own timeout.
READY_PROBE_TIMEOUT_SECONDS = 5.0

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT or settings.APP_ENV,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )

app = FastAPI(
    title="ParcelTrack API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
#
# Global default: 120 req/min per IP. Tighter per-route limits are applied
# via @limiter.limit("N/period") decorators on auth and mutation endpoints.

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
#
# Origins are driven entirely by the CORS_ALLOWED_ORIGINS env var.
# Production validates this is non-empty at Settings init time (config.py).
# Dev without an explicit list falls back to a permissive wildcard (no creds).

cors_origins = settings.cors_origins

if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Dev fallback: wildcard origin without credentials.
    # The CORS spec forbids '*' with allow_credentials=True, so we drop creds
    # in this branch instead of silently misconfiguring the browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ── Security headers ─────────────────────────────────────────────────────────
#
# Adds X-Frame-Options: DENY, X-Content-Type-Options: nosniff, HSTS (prod),
# Referrer-Policy, Permissions-Policy, X-Robots-Tag to every response.

app.add_middleware(SecurityHeadersMiddleware, is_production=settings.is_production)

# ── Request logging ──────────────────────────────────────────────────────────
#
# Outermost middleware — captures total request duration including all other
# middleware. Generates a per-request X-Request-ID for log correlation.

app.add_middleware(RequestLoggingMiddleware)


# ── Global exception handlers ─────────────────────────────────────────────────


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    if settings.is_production:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred"},
        )
    raise exc  # re-raise in dev so the full traceback surfaces


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
async def health():
    """Liveness probe — confirms the process is running and can serve HTTP."""
    return {"status": "ok", "env": settings.APP_ENV}


@app.get("/ready", tags=["health"])
async def ready(db: AsyncSession = Depends(get_db)):
    """
    Readiness probe — confirms the app can actually serve real requests.

    Checks database connectivity and Redis availability. Returns 503 if
    either dependency is unhealthy so the load balancer stops routing
    traffic here until the situation resolves.
    """
    from app.core.redis import get_redis_client

    checks: dict[str, str] = {}
    healthy = True

    # ── Database ──────────────────────────────────────────────────────────
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=READY_PROBE_TIMEOUT_SECONDS)
        checks["database"] = "ok"
    except TimeoutError:
        checks["database"] = f"timeout after {READY_PROBE_TIMEOUT_SECONDS}s"
        healthy = False
    except Exception as exc:
        checks["database"] = f"unavailable: {exc}"
        healthy = False

    # ── Redis ─────────────────────────────────────────────────────────────
    try:
        await asyncio.wait_for(get_redis_client().ping(), timeout=READY_PROBE_TIMEOUT_SECONDS)
        checks["redis"] = "ok"
    except TimeoutError:
        checks["redis"] = f"timeout after {READY_PROBE_TIMEOUT_SECONDS}s"
        healthy = False
    except Exception as exc:
        checks["redis"] = f"unavailable: {exc}"
        healthy = False

    if not healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "checks": checks},
        )

    return {"status": "ok", "checks": checks}


# ── Register all routers ──────────────────────────────────────────────────────

PREFIX = "/api/v1"

app.include_router(auth_router, prefix=PREFIX)
app.include_router(shipment_router, prefix=PREFIX)
app.include_router(po_router, prefix=PREFIX)
app.include_router(invoice_router, prefix=PREFIX)
app.include_router(payment_router, prefix=PREFIX)
app.include_router(bl_router, prefix=PREFIX)
app.include_router(vessel_router, prefix=PREFIX)
app.include_router(container_router, prefix=PREFIX)
app.include_router(customs_router, prefix=PREFIX)
app.include_router(clearing_router, prefix=PREFIX)
app.include_router(delivery_router, prefix=PREFIX)
app.include_router(doc_router, prefix=PREFIX)
app.include_router(notif_router, prefix=PREFIX)

# ── Docs gating ───────────────────────────────────────────────────────────────
#
# Built-in /docs, /redoc, /openapi.json are disabled on the FastAPI() above.
# We re-mount them here behind docs_guard, which only enforces admin auth in
# production. Non-prod environments stay open so the dev experience is
# unchanged. /openapi.json is gated alongside the HTML pages — without that,
# the schema would still be reachable from the browser even when /docs is locked.


async def docs_guard(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not get_settings().is_production:
        return
    user = await get_current_user(credentials=credentials, db=db)
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


docs_router = APIRouter(dependencies=[Depends(docs_guard)])


@docs_router.get("/openapi.json", include_in_schema=False)
async def openapi_schema():
    return app.openapi()


@docs_router.get("/docs", include_in_schema=False)
async def swagger_ui():
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} — Swagger UI")


@docs_router.get("/redoc", include_in_schema=False)
async def redoc_ui():
    return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} — ReDoc")


app.include_router(docs_router)


# ── Prometheus metrics ────────────────────────────────────────────────────────
#
# Exposes /metrics for Prometheus scraping. Excluded from OpenAPI schema and
# from its own instrumentation to avoid noisy self-referential metrics.

Instrumentator(
    should_group_status_codes=True,
    excluded_handlers=["/health", "/ready", "/metrics"],
).instrument(app).expose(app, include_in_schema=False)
