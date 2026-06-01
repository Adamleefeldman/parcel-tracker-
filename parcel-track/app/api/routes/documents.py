"""Document list / upload-URL / confirm / download routes.

Every endpoint is booking-scoped: the caller must be a member of the booking
the document's parent entity belongs to (admins always pass). The resolution
``(entity_type, entity_id) → booking`` lives in ``DocumentService`` and is
reused across all four endpoints.
"""

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
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.schemas import (
    ConfirmUploadRequest,
    DocumentListItem,
    DocumentOut,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services.document_service import DocumentService
from app.services.storage_service import StorageMimeMismatch, StorageObjectNotFound, StorageService

doc_router = APIRouter(prefix="/documents", tags=["documents"])


@doc_router.get("", response_model=PaginatedResponse[DocumentListItem])
async def list_documents(
    entity_type: DocumentEntityType,
    entity_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """List the documents attached to an entity, newest first.

    404 if the entity does not exist, 403 if the caller is not a member of its
    booking. Items omit ``download_url`` — call ``GET /documents/{id}/download-url``
    on tap to mint one.
    """
    await DocumentService.assert_document_access(db, entity_type, entity_id, actor)
    return await DocumentService.list_for_entity(db, entity_type, entity_id, pagination)


@doc_router.post("/upload-url", response_model=UploadUrlResponse)
@limiter.limit(RATE_LIMIT_UPLOAD)
async def get_upload_url(
    request: Request,
    body: UploadUrlRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """Step 1: client requests a pre-signed upload URL. Client uploads directly to storage."""
    await DocumentService.assert_document_access(db, body.entity_type, body.entity_id, actor)
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
    """Step 2: client confirms upload completed. API records the document in DB.

    Trust nothing the client says about the upload — HEAD the object in R2 and
    use the size/content-type the bucket actually reports. A missing object
    means the presigned PUT never succeeded; reject with 400 so the client
    retries instead of leaving an orphan ``Document`` row.
    """
    await DocumentService.assert_document_access(db, entity_type, entity_id, actor)
    try:
        meta = StorageService.verify_upload(body.file_key, expected_content_type=body.mime_type)
    except StorageObjectNotFound as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageMimeMismatch as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if meta["size"] > StorageService.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"file exceeds maximum size of {StorageService.MAX_FILE_SIZE_BYTES} bytes"),
        )

    doc = Document(
        uploaded_by=actor.id,
        entity_type=DocumentEntityType(entity_type),
        entity_id=entity_id,
        file_key=body.file_key,
        file_name=body.file_name,
        mime_type=meta["content_type"],
        file_size_bytes=meta["size"],
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
        "uploaded_by": doc.uploaded_by,
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
    await DocumentService.assert_document_access(db, doc.entity_type, doc.entity_id, actor)
    return {"download_url": StorageService.get_download_url(doc.file_key)}
