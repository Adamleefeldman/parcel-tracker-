import type { UserRole } from '../api/types/enums';
import { canManageDisputes, canUpdatePortStatus } from './permissions';

const ALL_ROLES: UserRole[] = ['admin', 'morocco_agent', 'uk_agent', 'customer'];

describe('canManageDisputes', () => {
  it('allows only admin', () => {
    expect(canManageDisputes('admin')).toBe(true);
    for (const role of ALL_ROLES.filter((r) => r !== 'admin')) {
      expect(canManageDisputes(role)).toBe(false);
    }
  });

  it('denies an undefined role (restrictive default)', () => {
    expect(canManageDisputes(undefined)).toBe(false);
  });
});

describe('canUpdatePortStatus', () => {
  it('allows admin + both agents, denies customer', () => {
    expect(canUpdatePortStatus('admin')).toBe(true);
    expect(canUpdatePortStatus('morocco_agent')).toBe(true);
    expect(canUpdatePortStatus('uk_agent')).toBe(true);
    expect(canUpdatePortStatus('customer')).toBe(false);
  });

  it('denies an undefined role (restrictive default)', () => {
    expect(canUpdatePortStatus(undefined)).toBe(false);
  });
});
