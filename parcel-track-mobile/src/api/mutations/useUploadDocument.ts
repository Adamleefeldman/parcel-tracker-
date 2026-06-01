/**
 * Document upload orchestration for one booking sub-entity.
 *
 * Drives the full presigned-URL flow in `mutationFn`:
 *   1. presign  — POST /documents/upload-url (body carries entity_type/entity_id)
 *   2. PUT       — `putFile` streams the bytes straight to R2's presigned URL,
 *                  with `Content-Type` === the presigned `mime_type` (the #1
 *                  failure cause if mismatched), reporting progress
 *   3. confirm   — POST /documents/confirm?entity_type=&entity_id= — the entity
 *                  pair rides the QUERY STRING; the body is only
 *                  {file_key, file_name, mime_type, file_size_bytes}
 *
 * No Idempotency-Key — document endpoints don't require one (unlike the
 * financial create endpoints). onSuccess invalidates the one sub-entity's
 * documents list so the new row appears.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import { documentsQueryKey } from '../queries/useDocuments';
import type { DocumentEntityType } from '../types/enums';
import type {
  ConfirmUploadRequest,
  DocumentOut,
  UploadUrlRequest,
  UploadUrlResponse,
} from '../types/document';
import { putFile } from '../../lib/upload';

export interface UploadDocumentVars {
  fileUri: string;
  fileName: string;
  /** MUST be threaded verbatim presign → PUT → confirm (it's in the R2 signature). */
  contentType: string;
  fileSize?: number;
  onProgress?: (fraction: number) => void;
}

export function useUploadDocument(entityType: DocumentEntityType, entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      fileUri,
      fileName,
      contentType,
      fileSize,
      onProgress,
    }: UploadDocumentVars): Promise<DocumentOut> => {
      const presignBody: UploadUrlRequest = {
        entity_type: entityType,
        entity_id: entityId,
        file_name: fileName,
        mime_type: contentType,
        ...(fileSize != null ? { file_size_bytes: fileSize } : {}),
      };
      const presign = await authedApiRequest<UploadUrlResponse>('/api/v1/documents/upload-url', {
        method: 'POST',
        body: presignBody,
      });

      await putFile({ url: presign.upload_url, fileUri, contentType, onProgress });

      const confirmBody: ConfirmUploadRequest = {
        file_key: presign.file_key,
        file_name: fileName,
        mime_type: contentType,
        ...(fileSize != null ? { file_size_bytes: fileSize } : {}),
      };
      const query = new URLSearchParams({ entity_type: entityType, entity_id: entityId });
      return authedApiRequest<DocumentOut>(`/api/v1/documents/confirm?${query.toString()}`, {
        method: 'POST',
        body: confirmBody,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentsQueryKey(entityType, entityId) });
    },
  });
}
