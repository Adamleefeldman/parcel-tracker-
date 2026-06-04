/**
 * Tests for the audit-log query helpers — key shape + path building (the
 * load-more window is encoded in limit/offset).
 */

import { auditLogsQueryKey, buildAuditLogsPath } from './useAuditLogs';

describe('auditLogsQueryKey', () => {
  it('returns ["audit-logs", filters] with an empty filters object by default', () => {
    expect(auditLogsQueryKey()).toEqual(['audit-logs', {}]);
  });

  it('keeps "audit-logs" first so invalidation by resource works', () => {
    expect(auditLogsQueryKey({ limit: 25, offset: 25 })[0]).toBe('audit-logs');
  });

  it('makes different windows distinct cache slots', () => {
    expect(auditLogsQueryKey({ limit: 25 })).not.toEqual(auditLogsQueryKey({ limit: 50 }));
  });
});

describe('buildAuditLogsPath', () => {
  it('returns the bare collection path when no filters are given', () => {
    expect(buildAuditLogsPath({})).toBe('/api/v1/audit-logs');
  });

  it('emits limit/offset for pagination — never the (backend-ignored) `page` param', () => {
    const path = buildAuditLogsPath({ limit: 25, offset: 25 });
    expect(path).toBe('/api/v1/audit-logs?limit=25&offset=25');
    expect(path).not.toContain('page');
  });
});
