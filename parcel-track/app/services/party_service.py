"""Party master service (Data-Foundation Pillar 3).

CRUD for `parties` (suppliers, freight forwarders, hauliers, warehouse
operators, customs brokers) and their child `party_bank_accounts`, plus the
V1 UAE Free-Zone watch report. Every write records an `AuditLog` row keyed by
the party `code`, mirroring the currency and legal-entity masters.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import PartyType
from app.db.models import LegalEntity, Party, PartyBankAccount, User
from app.schemas.schemas import (
    FreeZoneWatchOut,
    PartyBankAccountCreate,
    PartyCreate,
    PartyUpdate,
)
from app.services.audit_service import AuditService

# Country strings that mean "United Arab Emirates" for the Free-Zone watch.
_UAE_ALIASES = {
    "uae",
    "u.a.e.",
    "u.a.e",
    "united arab emirates",
    "united arab emirates (uae)",
    "emirates",
}


class PartyService:
    # ── reads ────────────────────────────────────────────────────────────────
    @staticmethod
    async def _load(db: AsyncSession, party_id: uuid.UUID) -> Party | None:
        """Load one party with its bank accounts eager-loaded (async-safe)."""
        result = await db.execute(
            select(Party).where(Party.id == party_id).options(selectinload(Party.bank_accounts))
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get(cls, db: AsyncSession, party_id: uuid.UUID) -> Party | None:
        return await cls._load(db, party_id)

    @classmethod
    async def get_or_404(cls, db: AsyncSession, party_id: uuid.UUID) -> Party:
        party = await cls._load(db, party_id)
        if party is None:
            raise HTTPException(404, "Party not found")
        return party

    @staticmethod
    async def get_by_type_code(db: AsyncSession, party_type: PartyType, code: str) -> Party | None:
        result = await db.execute(
            select(Party).where(Party.party_type == party_type, Party.code == code.strip().upper())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        *,
        party_type: PartyType | None = None,
        active_only: bool = False,
    ) -> list[Party]:
        stmt = (
            select(Party)
            .options(selectinload(Party.bank_accounts))
            .order_by(Party.party_type, Party.code)
        )
        if party_type is not None:
            stmt = stmt.where(Party.party_type == party_type)
        if active_only:
            stmt = stmt.where(Party.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── writes ───────────────────────────────────────────────────────────────
    @classmethod
    async def create(
        cls, db: AsyncSession, body: PartyCreate, actor: User, ip: str | None
    ) -> Party:
        if await cls.get_by_type_code(db, body.party_type, body.code) is not None:
            raise HTTPException(
                409, f"A {body.party_type.value} with code '{body.code}' already exists"
            )
        party = Party(
            party_type=body.party_type,
            code=body.code,
            name=body.name,
            country=body.country,
            default_currency_code=body.default_currency_code,
            default_payment_terms=body.default_payment_terms,
            email=body.email,
            phone=body.phone,
            is_active=True,
        )
        db.add(party)
        AuditService.record(
            db,
            actor_id=actor.id,
            action="party.created",
            entity_type="party",
            entity_code=party.code,
            new={
                "party_type": party.party_type.value,
                "code": party.code,
                "name": party.name,
                "country": party.country,
                "default_currency_code": party.default_currency_code,
                "default_payment_terms": party.default_payment_terms,
            },
            ip=ip,
        )
        await db.flush()
        return await cls.get_or_404(db, party.id)

    @classmethod
    async def update(
        cls,
        db: AsyncSession,
        party_id: uuid.UUID,
        body: PartyUpdate,
        actor: User,
        ip: str | None,
    ) -> Party:
        party = await cls.get_or_404(db, party_id)
        old = {
            "name": party.name,
            "country": party.country,
            "default_currency_code": party.default_currency_code,
            "default_payment_terms": party.default_payment_terms,
            "email": party.email,
            "phone": party.phone,
            "is_active": party.is_active,
        }
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(party, field, value)
        AuditService.record(
            db,
            actor_id=actor.id,
            action="party.updated",
            entity_type="party",
            entity_code=party.code,
            old=old,
            new={key: getattr(party, key) for key in old},
            ip=ip,
        )
        await db.flush()
        return await cls.get_or_404(db, party.id)

    @classmethod
    async def add_bank_account(
        cls,
        db: AsyncSession,
        party_id: uuid.UUID,
        body: PartyBankAccountCreate,
        actor: User,
        ip: str | None,
    ) -> PartyBankAccount:
        party = await cls.get_or_404(db, party_id)
        # First account is the default; an explicit is_default demotes the rest.
        is_default = body.is_default or len(party.bank_accounts) == 0
        if is_default:
            await db.execute(
                update(PartyBankAccount)
                .where(PartyBankAccount.party_id == party_id)
                .values(is_default=False)
            )
        account = PartyBankAccount(
            party_id=party_id,
            label=body.label,
            currency_code=body.currency_code,
            bank_name=body.bank_name,
            account_name=body.account_name,
            iban=body.iban,
            swift_bic=body.swift_bic,
            is_default=is_default,
        )
        db.add(account)
        AuditService.record(
            db,
            actor_id=actor.id,
            action="party.bank_account.added",
            entity_type="party",
            entity_code=party.code,
            new={
                "label": account.label,
                "currency_code": account.currency_code,
                "bank_name": account.bank_name,
                "account_name": account.account_name,
                "iban": cls._mask_iban(account.iban),  # avoid duplicating full IBANs into the log
                "swift_bic": account.swift_bic,
                "is_default": account.is_default,
            },
            ip=ip,
        )
        await db.flush()
        await db.refresh(account)
        return account

    # ── UAE Free-Zone watch (V1: report-only, country-based) ─────────────────
    @staticmethod
    def _is_uae(country: str | None) -> bool:
        return country is not None and country.strip().lower() in _UAE_ALIASES

    @staticmethod
    def _mask_iban(iban: str | None) -> str | None:
        if not iban:
            return None
        return f"****{iban[-4:]}"

    @staticmethod
    async def _free_zone_entities(db: AsyncSession) -> list[LegalEntity]:
        result = await db.execute(
            select(LegalEntity).where(
                LegalEntity.is_active.is_(True),
                LegalEntity.jurisdiction.ilike("%free zone%"),
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def free_zone_watch(cls, db: AsyncSession) -> list[FreeZoneWatchOut]:
        """Active counterparties that trip the Free-Zone watch: a UAE-based party
        while a UAE Free-Zone trading entity exists. Conservative by design — it
        flags any UAE counterparty for a human to review; it never blocks a write.
        """
        entities = await cls._free_zone_entities(db)
        if not entities:
            return []
        label = ", ".join(sorted(entity.code for entity in entities))
        reason = (
            f"Counterparty is UAE-based while trading entity [{label}] is a UAE "
            "Free Zone — review Free-Zone qualifying-income impact."
        )
        result = await db.execute(
            select(Party).where(Party.is_active.is_(True)).order_by(Party.party_type, Party.code)
        )
        return [
            FreeZoneWatchOut(
                party_id=party.id,
                party_type=party.party_type,
                code=party.code,
                name=party.name,
                country=party.country,
                reason=reason,
            )
            for party in result.scalars().all()
            if cls._is_uae(party.country)
        ]
