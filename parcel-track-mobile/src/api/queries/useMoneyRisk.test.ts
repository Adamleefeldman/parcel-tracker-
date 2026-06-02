/**
 * Tests for the money-risk hook. Same approach as `useSupplierPayments.test.ts`:
 * stub `useQuery` so the hook hands back its options object (no React renderer
 * under the node-env jest config), then probe the key, path, and `enabled`
 * gating. `canSeeMoneyRisk` is a pure predicate asserted directly.
 */

jest.mock('@tanstack/react-query', () => ({
  useQuery: jest.fn((options) => options),
}));
jest.mock('../authedClient', () => ({ authedApiRequest: jest.fn() }));

import { authedApiRequest } from '../authedClient';
import { canSeeMoneyRisk, moneyRiskQueryKey, useMoneyRisk } from './useMoneyRisk';

const mockAuthedApiRequest = authedApiRequest as jest.MockedFunction<typeof authedApiRequest>;

describe('moneyRiskQueryKey', () => {
  it('is the bare resource name (no filters — one call covers the dashboard)', () => {
    expect(moneyRiskQueryKey()).toEqual(['money-risk']);
  });
});

describe('canSeeMoneyRisk', () => {
  it('allows admin and uk_agent (the endpoint roles)', () => {
    expect(canSeeMoneyRisk('admin')).toBe(true);
    expect(canSeeMoneyRisk('uk_agent')).toBe(true);
  });

  it('denies morocco_agent and customer (they would 403)', () => {
    expect(canSeeMoneyRisk('morocco_agent')).toBe(false);
    expect(canSeeMoneyRisk('customer')).toBe(false);
  });

  it('denies an undefined role (restrictive default)', () => {
    expect(canSeeMoneyRisk(undefined)).toBe(false);
  });
});

describe('useMoneyRisk', () => {
  beforeEach(() => jest.clearAllMocks());

  it('hits the money-risk endpoint', async () => {
    mockAuthedApiRequest.mockResolvedValue({} as never);
    const query = useMoneyRisk({ enabled: true }) as any;
    await query.queryFn();
    expect(mockAuthedApiRequest).toHaveBeenCalledWith('/api/v1/money-risk');
  });

  it('is disabled for roles that cannot see money-risk (enabled: false)', () => {
    const query = useMoneyRisk({ enabled: false }) as any;
    expect(query.enabled).toBe(false);
  });

  it('is enabled when the caller passes enabled: true', () => {
    const query = useMoneyRisk({ enabled: true }) as any;
    expect(query.enabled).toBe(true);
  });

  it('defaults to enabled when no option is passed', () => {
    const query = useMoneyRisk() as any;
    expect(query.enabled).toBe(true);
  });
});
