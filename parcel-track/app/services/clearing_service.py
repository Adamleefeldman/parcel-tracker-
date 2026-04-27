"""Clearing docs service — upsert clearing documents and derive status."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ClearingDocsStatus, UserRole
from app.db.models import ClearingDocs, User
from app.schemas.schemas import ClearingDocsUpdate


class ClearingService:
    @staticmethod
    def _derive_status(
        has_customs_entry: bool,
        has_packing_list: bool,
        has_certificate_of_origin: bool,
    ) -> ClearingDocsStatus | None:
        """Derive status from document flags; returns None when none are set."""
        flags = [has_customs_entry, has_packing_list, has_certificate_of_origin]
        if all(flags):
            return ClearingDocsStatus.COMPLETE
        if any(flags):
            return ClearingDocsStatus.PARTIAL
        return None

    @staticmethod
    async def upsert(
        db: AsyncSession,
        shipment_id: uuid.UUID,
        body: ClearingDocsUpdate,
        actor: User,
    ) -> ClearingDocs:
        if actor.role not in (UserRole.ADMIN, UserRole.UK_AGENT):
            raise HTTPException(403, "Only admin or UK agent can update clearing docs")

        result = await db.execute(
            select(ClearingDocs).where(ClearingDocs.shipment_id == shipment_id)
        )
        docs = result.scalar_one_or_none()

        if not docs:
            docs = ClearingDocs(shipment_id=shipment_id, uploaded_by=actor.id)
            db.add(docs)
            await db.flush()

        for field, value in body.model_dump(exclude_none=True).items():
            setattr(docs, field, value)

        derived = ClearingService._derive_status(
            docs.has_customs_entry, docs.has_packing_list, docs.has_certificate_of_origin
        )
        if derived is not None:
            docs.status = derived

        return docs
