/**
 * Tests for the invites query helpers — key shape + path building, including
 * the `status` filter (default pending) that scopes the Admin console list.
 */

import { buildInvitesPath, invitesQueryKey } from './useInvites';

describe('invitesQueryKey', () => {
  it('returns ["invites", filters] with an empty filters object by default', () => {
    expect(invitesQueryKey()).toEqual(['invites', {}]);
  });

  it('keeps "invites" first so useSendInvite\'s prefix invalidation matches', () => {
    expect(invitesQueryKey({ status: 'pending' })[0]).toBe('invites');
  });
});

describe('buildInvitesPath', () => {
  it('returns the bare collection path when no filters are given', () => {
    expect(buildInvitesPath({})).toBe('/api/v1/invites');
  });

  it('emits the status filter', () => {
    expect(buildInvitesPath({ status: 'pending' })).toBe('/api/v1/invites?status=pending');
  });

  it('emits status + limit/offset, never a `page` param', () => {
    const path = buildInvitesPath({ status: 'all', limit: 50, offset: 0 });
    expect(path).toBe('/api/v1/invites?status=all&limit=50&offset=0');
    expect(path).not.toContain('page');
  });
});
