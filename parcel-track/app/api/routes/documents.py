"""Document upload-URL / confirm / download routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RATE_LIMIT_UPLOAD
from app.core.enums import DocumentEntityType
from app.db.database import get_db
from app.db.models import Document, User
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.schemas.schemas import (
    ConfirmUploadRequest,
    DocumentOut,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services.storage_service import StorageService

doc_router = APIRouter(prefix="/documents", tags=["documents"])


@doc_router.post("/upload-url", response_model=UploadUrlResponse)
@limiter.limit(RATE_LIMIT_UPLOAD)
async def get_upload_url(
    request: Request,
    body: UploadUrlRequest,
    actor: User = Depends(get_current_user),
):
    """Step 1: client requests a pre-signed upload URL. Client uploads directly to storage."""
    file_key = StorageService.generate_file_key(body.entity_type, body.entity_id, body.file_name)
    upload_url = StorageService.get_upload_url(file_key, body.mime_type)
    return UploadUrlResponse(
        upload_url=upload_url,
        file_key=file_key,
        expires_in_seconds=300,
    )


@doc_router.post("/confirm", response_model=DocumentOut)
async def confirm_upload(
    entity_type: str,
    entity_id: uuid.UUID,
    body: ConfirmUploadRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """Step 2: client confirms upload completed. API records the document in DB."""
    doc = Document(
        uploaded_by=actor.id,
        entity_type=DocumentEntityType(entity_type),
        entity_id=entity_id,
        file_key=body.file_key,
        file_name=body.file_name,
        mime_type=body.mime_type,
        file_size_bytes=body.file_size_bytes,
    )
    db.add(doc)
    await db.flush()
    download_url = StorageService.get_download_url(doc.file_key)
    # model_validate cannot produce download_url because it is computed, not a DB column.
    return {
        "id": doc.id,
        "entity_type": doc.entity_type,
        "entity_id": doc.entity_id,
        "file_name": doc.file_name,
        "mime_type": doc.mime_type,
        "file_size_bytes": doc.file_size_bytes,
        "download_url": download_url,
        "uploaded_at": doc.uploaded_at,
    }


@doc_router.get("/{document_id}/download-url")
async def get_download_url(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"download_url": StorageService.get_download_url(doc.file_key)}
