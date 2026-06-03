/**
 * Tests for the brokers query helpers — key shape + path building. The hook
 * itself needs a React renderer (not stood up here, per Testing policy); the
 * pure helpers are what every other hook copies, so pin them down.
 */

import { brokersQueryKey, buildBrokersPath } from './useBrokers';

describe('brokersQueryKey', () => {
  it('returns ["brokers", filters] with an empty filters object by default', () => {
    expect(brokersQueryKey()).toEqual(['brokers', {}]);
  });

  it('keeps "brokers" as the first element so invalidation by resource works', () => {
    expect(brokersQueryKey({ limit: 50, offset: 50 })[0]).toBe('brokers');
  });
});

describe('buildBrokersPath', () => {
  it('returns the bare collection path when no filters are given', () => {
    expect(buildBrokersPath({})).toBe('/api/v1/brokers');
  });

  it('emits limit/offset for pagination — never the (backend-ignored) `page` param', () => {
    const path = buildBrokersPath({ limit: 50, offset: 50 });
    expect(path).toBe('/api/v1/brokers?limit=50&offset=50');
    expect(path).not.toContain('page');
  });

  it('includes offset=0 since it is defined', () => {
    expect(buildBrokersPath({ offset: 0, limit: 25 })).toBe('/api/v1/brokers?limit=25&offset=0');
  });
});
