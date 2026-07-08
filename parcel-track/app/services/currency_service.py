"""Currency master service (Data-Foundation Pillar 1a).

CRUD over the `currencies` reference table (spec §2.2). The legacy `Currency`
enum is untouched; this table drives NEW currency-referencing columns.

`is_base` is fixed by the migration seed (USD) and cannot be set or toggled
through the API in 1a, so exactly one base currency is guaranteed. Writes are
audited through the shared `AuditService`.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CurrencyRef, User
from app.schemas.schemas import CurrencyCreate, CurrencyUpdate
from app.services.audit_service import AuditService


class CurrencyService:
    @staticmethod
    async def list_all(db: AsyncSession, *, active_only: bool = False) -> list[CurrencyRef]:
        stmt = select(CurrencyRef).order_by(CurrencyRef.code)
        if active_only:
            stmt = stmt.where(CurrencyRef.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, code: str) -> CurrencyRef | None:
        result = await db.execute(select(CurrencyRef).where(CurrencyRef.code == code.upper()))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession, body: CurrencyCreate, actor: User, ip: str | None
    ) -> CurrencyRef:
        if await CurrencyService.get(db, body.code) is not None:
            raise HTTPException(409, f"Currency {body.code} already exists")
        currency = CurrencyRef(
            code=body.code,
            name=body.name,
            symbol=body.symbol,
            minor_units=body.minor_units,
            is_base=False,
            is_active=True,
        )
        db.add(currency)
        AuditService.record(
            db,
            actor_id=actor.id,
            action="currency.created",
            entity_type="currency",
            entity_code=currency.code,
            new={
                "code": currency.code,
                "name": currency.name,
                "symbol": currency.symbol,
                "minor_units": currency.minor_units,
            },
            ip=ip,
        )
        await db.flush()
        await db.refresh(currency)
        return currency

    @staticmethod
    async def update(
        db: AsyncSession, code: str, body: CurrencyUpdate, actor: User, ip: str | None
    ) -> CurrencyRef:
        currency = await CurrencyService.get(db, code)
        if currency is None:
            raise HTTPException(404, "Currency not found")
        old = {
            "name": currency.name,
            "symbol": currency.symbol,
            "minor_units": currency.minor_units,
            "is_active": currency.is_active,
        }
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(currency, field, value)
        AuditService.record(
            db,
            actor_id=actor.id,
            action="currency.updated",
            entity_type="currency",
            entity_code=currency.code,
            old=old,
            new={
                "name": currency.name,
                "symbol": currency.symbol,
                "minor_units": currency.minor_units,
                "is_active": currency.is_active,
            },
            ip=ip,
        )
        await db.flush()
        await db.refresh(currency)
        return currency
