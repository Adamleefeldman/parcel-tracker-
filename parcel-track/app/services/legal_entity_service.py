"""Legal-entity master service (Data-Foundation Pillar 2).

CRUD over the `legal_entities` reference table (spec §3) plus `get_default` —
the singleton lookup the transaction services use to tag every new money /
shipment row with its owning entity.

`is_default` is fixed by the migration seed (exactly one true) and is NOT
settable through the API — mirroring `currencies.is_base`. Writes are audited
through the shared `AuditService`, keyed by the entity `code` (stable, human
readable) the same way currency master writes are.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LegalEntity, User
from app.schemas.schemas import LegalEntityCreate, LegalEntityUpdate
from app.services.audit_service import AuditService


class LegalEntityService:
    @staticmethod
    async def list_all(db: AsyncSession, *, active_only: bool = False) -> list[LegalEntity]:
        stmt = select(LegalEntity).order_by(LegalEntity.code)
        if active_only:
            stmt = stmt.where(LegalEntity.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, entity_id: uuid.UUID) -> LegalEntity | None:
        result = await db.execute(select(LegalEntity).where(LegalEntity.id == entity_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(db: AsyncSession, code: str) -> LegalEntity | None:
        result = await db.execute(select(LegalEntity).where(LegalEntity.code == code.upper()))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_default(db: AsyncSession) -> LegalEntity | None:
        """The single seeded default entity. New transactions tag to this when
        the caller doesn't specify one (the migration guarantees exactly one)."""
        result = await db.execute(select(LegalEntity).where(LegalEntity.is_default.is_(True)))
        return result.scalar_one_or_none()

    @staticmethod
    async def default_id(db: AsyncSession) -> uuid.UUID | None:
        """`get_default().id`, or None if the table is unseeded (graceful — the
        `legal_entity_id` columns are nullable, mirroring the FX 'no rate' path)."""
        entity = await LegalEntityService.get_default(db)
        return entity.id if entity is not None else None

    @staticmethod
    async def create(
        db: AsyncSession, body: LegalEntityCreate, actor: User, ip: str | None
    ) -> LegalEntity:
        if await LegalEntityService.get_by_code(db, body.code) is not None:
            raise HTTPException(409, f"Legal entity {body.code} already exists")
        entity = LegalEntity(
            code=body.code,
            legal_name=body.legal_name,
            display_name=body.display_name,
            jurisdiction=body.jurisdiction,
            base_currency_code=body.base_currency_code,
            is_default=False,
            is_active=True,
        )
        db.add(entity)
        AuditService.record(
            db,
            actor_id=actor.id,
            action="legal_entity.created",
            entity_type="legal_entity",
            entity_code=entity.code,
            new={
                "code": entity.code,
                "legal_name": entity.legal_name,
                "display_name": entity.display_name,
                "jurisdiction": entity.jurisdiction,
                "base_currency_code": entity.base_currency_code,
            },
            ip=ip,
        )
        await db.flush()
        await db.refresh(entity)
        return entity

    @staticmethod
    async def update(
        db: AsyncSession,
        entity_id: uuid.UUID,
        body: LegalEntityUpdate,
        actor: User,
        ip: str | None,
    ) -> LegalEntity:
        entity = await LegalEntityService.get(db, entity_id)
        if entity is None:
            raise HTTPException(404, "Legal entity not found")
        old = {
            "legal_name": entity.legal_name,
            "display_name": entity.display_name,
            "jurisdiction": entity.jurisdiction,
            "base_currency_code": entity.base_currency_code,
            "is_active": entity.is_active,
        }
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        AuditService.record(
            db,
            actor_id=actor.id,
            action="legal_entity.updated",
            entity_type="legal_entity",
            entity_code=entity.code,
            old=old,
            new={
                "legal_name": entity.legal_name,
                "display_name": entity.display_name,
                "jurisdiction": entity.jurisdiction,
                "base_currency_code": entity.base_currency_code,
                "is_active": entity.is_active,
            },
            ip=ip,
        )
        await db.flush()
        await db.refresh(entity)
        return entity
