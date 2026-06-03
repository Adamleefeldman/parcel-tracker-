/**
 * Tests for the port-templates query key. It's a single-slot key (no filters —
 * the endpoint returns a plain list), matching the `useMoneyRisk` convention, so
 * the mutation can invalidate `['port-templates']` to refetch it.
 */

import { portTemplatesQueryKey } from './usePortTemplates';

describe('portTemplatesQueryKey', () => {
  it('is the bare resource name (no filters)', () => {
    expect(portTemplatesQueryKey()).toEqual(['port-templates']);
  });
});
