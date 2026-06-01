/**
 * Imperative fetch of a presigned GET URL for a single document.
 *
 * GET /api/v1/documents/{id}/download-url → { download_url }. The URL is
 * short-lived (~15 min) and single-use-ish, so this is NOT a cached query — we
 * mint a fresh one on each tap, right before opening it in the system browser.
 * Booking-scoped server-side (403 for non-members).
 */

import { authedApiRequest } from '../authedClient';

export async function getDownloadUrl(documentId: string): Promise<string> {
  const { download_url } = await authedApiRequest<{ download_url: string }>(
    `/api/v1/documents/${documentId}/download-url`,
  );
  return download_url;
}
