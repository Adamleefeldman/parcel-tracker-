"""Port-template routes (P1.3).

A PortTemplate holds the default detention/demurrage free-days + rates for a
UK discharge port. Admin-only upsert; any authenticated user can list (so the
templates show up in pickers and feed the booking-confirmation defaults).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UKPort
from app.db.database import get_db
from app.db.models import User
from app.middleware.auth import get_current_user, require_admin
from app.schemas.schemas import PortTemplateOut, PortTemplateUpsert
from app.services.port_template_service import PortTemplateService

port_template_router = APIRouter(prefix="/port-templates", tags=["port-templates"])


@port_template_router.get("", response_model=list[PortTemplateOut])
async def list_port_templates(
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return await PortTemplateService.list_all(db)


@port_template_router.put("/{port}", response_model=PortTemplateOut)
async def upsert_port_template(
    port: UKPort,
    body: PortTemplateUpsert,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    return await PortTemplateService.upsert(db, port, body)
