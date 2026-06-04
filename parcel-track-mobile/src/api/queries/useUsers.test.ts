/**
 * Tests for the users query helpers — key shape + path building. The hook
 * needs a React renderer (not stood up here, per Testing policy); the pure
 * helpers are the contract worth pinning down.
 */

import { buildUsersPath, usersQueryKey } from './useUsers';

describe('usersQueryKey', () => {
  it('returns ["users", filters] with an empty filters object by default', () => {
    expect(usersQueryKey()).toEqual(['users', {}]);
  });

  it('keeps "users" first so invalidation by resource works', () => {
    expect(usersQueryKey({ limit: 200 })[0]).toBe('users');
  });
});

describe('buildUsersPath', () => {
  it('returns the bare collection path when no filters are given', () => {
    expect(buildUsersPath({})).toBe('/api/v1/users');
  });

  it('emits limit/offset for pagination — never the (backend-ignored) `page` param', () => {
    const path = buildUsersPath({ limit: 200, offset: 0 });
    expect(path).toBe('/api/v1/users?limit=200&offset=0');
    expect(path).not.toContain('page');
  });
});
