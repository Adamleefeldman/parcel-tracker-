/**
 * Query-key + path-builder shape tests for the documents list hook. As with
 * the other query tests, we don't render the hook (node-env jest) — we assert
 * the exported builders: the key scopes by (entity_type, entity_id) and the
 * path emits both as query params.
 */

import { buildDocumentsPath, documentsQueryKey } from './useDocuments';

describe('documents query', () => {
  it('builds the key as [resource, entityType, entityId]', () => {
    expect(documentsQueryKey('invoice', 'e-1')).toEqual(['documents', 'invoice', 'e-1']);
  });

  it('builds the path with entity_type + entity_id query params', () => {
    expect(buildDocumentsPath('bill_of_lading', 'bl-7')).toBe(
      '/api/v1/documents?entity_type=bill_of_lading&entity_id=bl-7',
    );
  });

  it('produces distinct keys per entity type and id', () => {
    expect(documentsQueryKey('invoice', 'e-1')).not.toEqual(documentsQueryKey('payment', 'e-1'));
    expect(documentsQueryKey('invoice', 'e-1')).not.toEqual(documentsQueryKey('invoice', 'e-2'));
  });
});
