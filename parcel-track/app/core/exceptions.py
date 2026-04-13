"""
Shared exception helpers.

Provides a context manager that translates SQLAlchemy IntegrityError (e.g.
unique constraint violations) into a clean 409 HTTP response, so callers
don't have to repeat the same try/except pattern on every mutation route.

Usage:

    async with handle_integrity_error("BL number already exists"):
        db.add(bl)
        await db.flush()
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError


@asynccontextmanager
async def handle_integrity_error(detail: str):
    """
    Async context manager — catches IntegrityError and raises HTTP 409.

    The caller should still let the session roll back (the db dependency
    handles that automatically), so we just re-raise as HTTPException.
    """
    try:
        yield
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from None
