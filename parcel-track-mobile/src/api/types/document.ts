/**
 * Document attachment types. Mirror the backend Pydantic schemas
 * (`UploadUrlRequest`/`UploadUrlResponse`/`ConfirmUploadRequest`/`DocumentOut`/
 * `DocumentListItem` in `parcel-track/app/schemas/schemas.py`).
 *
 * Documents are entity-scoped: every shape carries an `(entity_type, entity_id)`
 * pair identifying the booking sub-entity the file hangs off. The flow is
 * presign → PUT-to-R2 → confirm → list/download — no Idempotency-Key anywhere
 * (unlike the financial create endpoints).
 */

import type { DocumentEntityType } from './enums';

/** Request body for `POST /documents/upload-url` (step 1, presign). */
export interface UploadUrlRequest {
  entity_type: DocumentEntityType;
  entity_id: string;
  file_name: string;
  mime_type: string;
  file_size_bytes?: number;
}

/** Response from `POST /documents/upload-url`. `upload_url` is a presigned PUT. */
export interface UploadUrlResponse {
  upload_url: string;
  file_key: string;
  expires_in_seconds: number;
}

/**
 * Body for `POST /documents/confirm` (step 3). `entity_type`/`entity_id` ride
 * the QUERY STRING, not this body — see `useUploadDocument`.
 */
export interface ConfirmUploadRequest {
  file_key: string;
  file_name: string;
  mime_type: string;
  file_size_bytes?: number;
}

/** Full document record returned by confirm (includes a fresh presigned GET URL). */
export interface DocumentOut {
  id: string;
  entity_type: DocumentEntityType;
  entity_id: string;
  file_name: string;
  mime_type: string;
  file_size_bytes: number | null;
  download_url: string;
  uploaded_by: string;
  uploaded_at: string;
}

/**
 * List-view item from `GET /documents`. Deliberately omits `download_url` —
 * the server mints one per row only on tap (`GET /documents/{id}/download-url`)
 * to avoid N storage round-trips for URLs most of which are never clicked.
 */
export interface DocumentListItem {
  id: string;
  entity_type: DocumentEntityType;
  entity_id: string;
  file_name: string;
  mime_type: string;
  file_size_bytes: number | null;
  uploaded_by: string;
  uploaded_at: string;
}
