"""
Reusable pagination primitives for list endpoints.

Usage in a route handler:

    from app.schemas.pagination import PaginationParams, PaginatedResponse

    @router.get("", response_model=PaginatedResponse[ItemOut])
    async def list_items(
        pagination: PaginationParams = Depends(),
        db: AsyncSession = Depends(get_db),
    ):
        query = select(Item)
        return await paginate(db, query, pagination, ItemOut)
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T", bound=BaseModel)

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


# ── Dependency ────────────────────────────────────────────────────────────────


class PaginationParams:
    """
    Inject as a FastAPI dependency to extract `offset` and `limit` from
    query parameters with sane defaults and clamped maximums.

        pagination: PaginationParams = Depends()
    """

    def __init__(
        self,
        offset: int = Query(0, ge=0, description="Number of items to skip"),
        limit: int = Query(
            DEFAULT_PAGE_SIZE,
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Max items to return (1-{MAX_PAGE_SIZE})",
        ),
    ) -> None:
        self.offset = offset
        self.limit = limit


# ── Response envelope ─────────────────────────────────────────────────────────


class PaginatedResponse(BaseModel, Generic[T]):  # noqa: UP046
    """Paginated list envelope returned by every list endpoint."""

    items: list[T]
    total: int
    offset: int
    limit: int


# ── Helper ────────────────────────────────────────────────────────────────────


async def paginate(
    db: AsyncSession,
    query: Select,
    pagination: PaginationParams,
    *,
    items: Sequence | None = None,
) -> dict:
    """
    Execute a paginated query and return data in the PaginatedResponse shape.

    If `items` is provided (pre-fetched rows), only the count query runs.
    Otherwise both count + data queries are executed.

    Returns a plain dict (FastAPI's response_model handles serialisation).
    """
    # Count total rows matching the query (before offset/limit).
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    if items is None:
        data_query = query.offset(pagination.offset).limit(pagination.limit)
        result = await db.execute(data_query)
        items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "offset": pagination.offset,
        "limit": pagination.limit,
    }
