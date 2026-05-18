"""Broker + Company (end-buyer) CRUD.

These are the customer-side parties referenced from Container. Kept minimal in
P0.2 — full customer CRM lives in a deferred phase. Admin-only writes; any
authenticated user can list/read (so brokers and customers show up in pickers).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import handle_integrity_error
from app.db.database import get_db
from app.db.models import Broker, Company, User
from app.middleware.auth import get_current_user, require_admin
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.schemas.schemas import BrokerCreate, BrokerOut, CompanyCreate, CompanyOut

broker_router = APIRouter(prefix="/brokers", tags=["brokers"])
company_router = APIRouter(prefix="/companies", tags=["companies"])


# ── Brokers ──────────────────────────────────────────────────────────────────


@broker_router.post("", response_model=BrokerOut)
async def create_broker(
    body: BrokerCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    async with handle_integrity_error("A broker with this code already exists"):
        broker = Broker(code=body.code, name=body.name, phone=body.phone)
        db.add(broker)
        await db.flush()
    await db.refresh(broker)
    return broker


@broker_router.get("", response_model=PaginatedResponse[BrokerOut])
async def list_brokers(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await paginate(db, select(Broker), pagination)


@broker_router.get("/{broker_id}", response_model=BrokerOut)
async def get_broker(
    broker_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    result = await db.execute(select(Broker).where(Broker.id == broker_id))
    broker = result.scalar_one_or_none()
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    return broker


# ── Companies (end-buyers) ───────────────────────────────────────────────────


@company_router.post("", response_model=CompanyOut)
async def create_company(
    body: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    async with handle_integrity_error("A company with this legal_name already exists"):
        company = Company(
            legal_name=body.legal_name,
            aliases=body.aliases,
            registration_no=body.registration_no,
            vat_no=body.vat_no,
            default_address=body.default_address,
        )
        db.add(company)
        await db.flush()
    await db.refresh(company)
    return company


@company_router.get("", response_model=PaginatedResponse[CompanyOut])
async def list_companies(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await paginate(db, select(Company), pagination)


@company_router.get("/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company
