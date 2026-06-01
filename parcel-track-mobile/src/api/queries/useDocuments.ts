/**
 * Documents-list query for a booking sub-entity.
 *
 * GET /api/v1/documents?entity_type=&entity_id=&limit=&offset= →
 * PaginatedResponse<DocumentListItem>, newest-first. Booking-scoped server-side
 * (a non-member of the parent booking gets a 403).
 *
 * Query-key convention: resource name first, then the (entity_type, entity_id)
 * pair that scopes the collection — so each sub-entity's list is its own cache
 * slot and the upload mutation invalidates exactly one of them.
 */

import { useQuery } from '@tanstack/react-query';

import { authedApiRequest } from '../authedClient';
import type { DocumentEntityType } from '../types/enums';
import type { DocumentListItem } from '../types/document';
import type { PaginatedResponse } from './useBookings';

export function documentsQueryKey(
  entityType: DocumentEntityType,
  entityId: string,
): readonly unknown[] {
  return ['documents', entityType, entityId] as const;
}

export function buildDocumentsPath(entityType: DocumentEntityType, entityId: string): string {
  const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId });
  return `/api/v1/documents?${params.toString()}`;
}

export function useDocuments(entityType: DocumentEntityType, entityId: string) {
  return useQuery({
    queryKey: documentsQueryKey(entityType, entityId),
    queryFn: () =>
      authedApiRequest<PaginatedResponse<DocumentListItem>>(
        buildDocumentsPath(entityType, entityId),
      ),
    enabled: !!entityId,
  });
}
