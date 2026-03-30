"""
Application entry point.
All routers registered here. Exception handlers provide consistent error shape.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes.routes import (
    auth_router, shipment_router, po_router,
    invoice_router, payment_router, bl_router,
    vessel_router, container_router, customs_router,
    clearing_router, delivery_router, doc_router,
    notif_router,
)

settings = get_settings()

app = FastAPI(
    title="ParcelTrack API",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# ── CORS (lock down in production) ────────────────────────────────────────────

origins = ["*"] if not settings.is_production else [
    "https://yourapp.com",  # replace with actual origin in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    if settings.is_production:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred"},
        )
    raise exc  # re-raise in dev so the full traceback surfaces


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "env": settings.APP_ENV}


# ── Register all routers ──────────────────────────────────────────────────────

PREFIX = "/api/v1"

app.include_router(auth_router,       prefix=PREFIX)
app.include_router(shipment_router,   prefix=PREFIX)
app.include_router(po_router,         prefix=PREFIX)
app.include_router(invoice_router,    prefix=PREFIX)
app.include_router(payment_router,    prefix=PREFIX)
app.include_router(bl_router,         prefix=PREFIX)
app.include_router(vessel_router,     prefix=PREFIX)
app.include_router(container_router,  prefix=PREFIX)
app.include_router(customs_router,    prefix=PREFIX)
app.include_router(clearing_router,   prefix=PREFIX)
app.include_router(delivery_router,   prefix=PREFIX)
app.include_router(doc_router,        prefix=PREFIX)
app.include_router(notif_router,      prefix=PREFIX)
