/**
 * Tests for the companies (end customers) query helpers — key shape + path.
 */

import { buildCompaniesPath, companiesQueryKey } from './useCompanies';

describe('companiesQueryKey', () => {
  it('returns ["companies", filters] with an empty filters object by default', () => {
    expect(companiesQueryKey()).toEqual(['companies', {}]);
  });

  it('keeps "companies" as the first element so invalidation by resource works', () => {
    expect(companiesQueryKey({ limit: 50 })[0]).toBe('companies');
  });
});

describe('buildCompaniesPath', () => {
  it('returns the bare collection path when no filters are given', () => {
    expect(buildCompaniesPath({})).toBe('/api/v1/companies');
  });

  it('emits limit/offset for pagination — never `page`', () => {
    const path = buildCompaniesPath({ limit: 50, offset: 50 });
    expect(path).toBe('/api/v1/companies?limit=50&offset=50');
    expect(path).not.toContain('page');
  });

  it('includes offset=0 since it is defined', () => {
    expect(buildCompaniesPath({ offset: 0, limit: 25 })).toBe(
      '/api/v1/companies?limit=25&offset=0',
    );
  });
});
