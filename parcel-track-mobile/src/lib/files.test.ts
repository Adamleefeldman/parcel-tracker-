import {
  ALLOWED_CONTENT_TYPES,
  MAX_UPLOAD_BYTES,
  formatBytes,
  isAllowedContentType,
  validateFile,
} from './files';

describe('files — allowlist + size cap mirror the backend', () => {
  it('caps at 50 MB', () => {
    expect(MAX_UPLOAD_BYTES).toBe(50 * 1024 * 1024);
  });

  it('allows exactly the backend MIME types', () => {
    expect([...ALLOWED_CONTENT_TYPES].sort()).toEqual(
      [
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/webp',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
      ].sort(),
    );
  });

  it('recognises allowed vs disallowed content types', () => {
    expect(isAllowedContentType('application/pdf')).toBe(true);
    expect(isAllowedContentType('image/gif')).toBe(false);
  });
});

describe('validateFile', () => {
  it('returns null for an acceptable file', () => {
    expect(validateFile({ size: 1024, contentType: 'application/pdf' })).toBeNull();
  });

  it('rejects a disallowed type', () => {
    expect(validateFile({ size: 1024, contentType: 'image/gif' })).toMatch(/isn’t supported/);
  });

  it('rejects an oversize file', () => {
    expect(
      validateFile({ size: MAX_UPLOAD_BYTES + 1, contentType: 'application/pdf' }),
    ).toMatch(/too large/);
  });

  it('accepts a file at exactly the cap', () => {
    expect(validateFile({ size: MAX_UPLOAD_BYTES, contentType: 'application/pdf' })).toBeNull();
  });

  it('accepts an allowed type when size is unknown', () => {
    expect(validateFile({ size: null, contentType: 'image/png' })).toBeNull();
  });
});

describe('formatBytes', () => {
  it('formats across units', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(50 * 1024 * 1024)).toBe('50 MB');
  });

  it('returns a dash for missing/invalid input', () => {
    expect(formatBytes(null)).toBe('—');
    expect(formatBytes(undefined)).toBe('—');
    expect(formatBytes(-1)).toBe('—');
  });
});
