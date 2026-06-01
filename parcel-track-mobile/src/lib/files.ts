/**
 * File-validation + formatting helpers for document uploads.
 *
 * The size cap and MIME allowlist mirror the backend EXACTLY
 * (`StorageService.MAX_FILE_SIZE_BYTES` + `StorageService.ALLOWED_MIME_TYPES`
 * in `parcel-track/app/services/storage_service.py`). Client-side validation
 * is a courtesy — the server re-checks the object it HEADs in R2 (the source
 * of truth) and rejects with 400/413 regardless — but blocking obviously-bad
 * picks before we burn a presign round-trip is the better UX.
 */

/** Maximum upload size — must match the backend's 50 MB cap. */
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

/** Accepted MIME types — must match the backend's allowlist verbatim. */
export const ALLOWED_CONTENT_TYPES = [
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/webp',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // xlsx
  'application/vnd.ms-excel', // xls
] as const;

export type AllowedContentType = (typeof ALLOWED_CONTENT_TYPES)[number];

export function isAllowedContentType(contentType: string): contentType is AllowedContentType {
  return (ALLOWED_CONTENT_TYPES as readonly string[]).includes(contentType);
}

/**
 * Validate a picked file against the backend's rules. Returns a user-facing
 * error message, or `null` when the file is acceptable.
 */
export function validateFile({
  size,
  contentType,
}: {
  size: number | null | undefined;
  contentType: string;
}): string | null {
  if (!isAllowedContentType(contentType)) {
    return 'That file type isn’t supported. Use a PDF, image, or spreadsheet.';
  }
  if (size != null && size > MAX_UPLOAD_BYTES) {
    return `File is too large (${formatBytes(size)}). The maximum is ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  }
  return null;
}

/**
 * Human-readable byte count: `"512 B"`, `"1.4 KB"`, `"23.8 MB"`. Uses 1024-step
 * units and trims a trailing `.0`. Cosmetic only — never round-trips anywhere.
 */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const rounded = value >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `${text} ${units[unitIndex]}`;
}
