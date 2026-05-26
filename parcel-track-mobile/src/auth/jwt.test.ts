/**
 * Tests for JWT payload decoding (client-side, signature NOT verified).
 */

import { decodeUserFromToken } from './jwt';

function base64url(input: string): string {
  return Buffer.from(input, 'utf8')
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

function makeToken(payload: Record<string, unknown>): string {
  const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = base64url(JSON.stringify(payload));
  return `${header}.${body}.sig-doesnt-matter`;
}

describe('decodeUserFromToken', () => {
  it('extracts id + role from a backend-shaped access token', () => {
    const token = makeToken({
      sub: '00000000-0000-0000-0000-000000000001',
      role: 'agent_morocco',
      type: 'access',
      exp: 1_900_000_000,
      jti: 'abc',
    });

    expect(decodeUserFromToken(token)).toEqual({
      id: '00000000-0000-0000-0000-000000000001',
      role: 'agent_morocco',
    });
  });

  it('returns null for a malformed token', () => {
    expect(decodeUserFromToken('not-a-jwt')).toBeNull();
  });

  it('returns null when sub or role are missing', () => {
    const token = makeToken({ type: 'access', exp: 1_900_000_000 });
    expect(decodeUserFromToken(token)).toBeNull();
  });
});
