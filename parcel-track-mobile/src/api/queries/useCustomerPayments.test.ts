/**
 * Query-key shape tests for the customer-payment hooks. We don't render the
 * hooks (no React renderer under the node-env jest config) — we test the
 * exported key builders, and specifically the prefix relationship that lets a
 * single invalidate hit both the list and the aggregate (see the create
 * mutation's onSuccess).
 */

import { customerPaymentAggregateQueryKey } from './useCustomerPaymentAggregate';
import { customerPaymentsQueryKey } from './useCustomerPayments';

describe('customer-payment query keys', () => {
  it('builds the list key as [resource, bookingId, containerId]', () => {
    expect(customerPaymentsQueryKey('b-1', 'c-2')).toEqual(['customer-payments', 'b-1', 'c-2']);
  });

  it('builds the aggregate key as the list key plus a trailing "aggregate"', () => {
    expect(customerPaymentAggregateQueryKey('b-1', 'c-2')).toEqual([
      'customer-payments',
      'b-1',
      'c-2',
      'aggregate',
    ]);
  });

  it('makes the list key a prefix of the aggregate key (so one invalidate hits both)', () => {
    const list = customerPaymentsQueryKey('b-1', 'c-2');
    const aggregate = customerPaymentAggregateQueryKey('b-1', 'c-2');
    expect(aggregate.slice(0, list.length)).toEqual([...list]);
  });

  it('produces distinct keys for different containers', () => {
    expect(customerPaymentsQueryKey('b-1', 'c-2')).not.toEqual(
      customerPaymentsQueryKey('b-1', 'c-9'),
    );
  });
});
