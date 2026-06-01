import {
  defaultSupplierPaymentFormValues,
  supplierPaymentSchema,
  toCreateBody,
  type SupplierPaymentFormValues,
} from './supplierPaymentSchema';

const valid: SupplierPaymentFormValues = {
  swift_ref: 'SWIFT-123',
  payment_date: '2026-06-01',
  amount: '8000.00',
  payment_type: 'partial',
  bank_name: 'HSBC',
  notes: 'deposit wire',
};

describe('supplierPaymentSchema', () => {
  it('accepts a fully valid set of values', () => {
    expect(supplierPaymentSchema.safeParse(valid).success).toBe(true);
  });

  it('rejects a blank swift_ref', () => {
    expect(supplierPaymentSchema.safeParse({ ...valid, swift_ref: '' }).success).toBe(false);
    expect(supplierPaymentSchema.safeParse({ ...valid, swift_ref: '   ' }).success).toBe(false);
  });

  it('rejects a missing / malformed payment_date', () => {
    expect(supplierPaymentSchema.safeParse({ ...valid, payment_date: '' }).success).toBe(false);
    expect(supplierPaymentSchema.safeParse({ ...valid, payment_date: '01/06/2026' }).success).toBe(
      false,
    );
  });

  it('rejects amount ≤ 0, non-decimal, or > 2 decimals', () => {
    expect(supplierPaymentSchema.safeParse({ ...valid, amount: '0' }).success).toBe(false);
    expect(supplierPaymentSchema.safeParse({ ...valid, amount: '0.00' }).success).toBe(false);
    expect(supplierPaymentSchema.safeParse({ ...valid, amount: 'abc' }).success).toBe(false);
    expect(supplierPaymentSchema.safeParse({ ...valid, amount: '10.123' }).success).toBe(false);
    expect(supplierPaymentSchema.safeParse({ ...valid, amount: '' }).success).toBe(false);
  });

  it('accepts a positive amount with up to 2 decimals', () => {
    expect(supplierPaymentSchema.safeParse({ ...valid, amount: '0.01' }).success).toBe(true);
    expect(supplierPaymentSchema.safeParse({ ...valid, amount: '100' }).success).toBe(true);
  });

  it('rejects a payment_type outside the allowed set (incl. the blank default)', () => {
    expect(supplierPaymentSchema.safeParse({ ...valid, payment_type: '' }).success).toBe(false);
    expect(supplierPaymentSchema.safeParse({ ...valid, payment_type: 'wire' }).success).toBe(false);
  });

  it('accepts each allowed payment_type', () => {
    for (const t of ['full', 'partial', 'deposit']) {
      expect(supplierPaymentSchema.safeParse({ ...valid, payment_type: t }).success).toBe(true);
    }
  });

  it('treats bank_name and notes as optional (blank is valid)', () => {
    expect(supplierPaymentSchema.safeParse({ ...valid, bank_name: '', notes: '' }).success).toBe(
      true,
    );
  });

  it('has a blank-amount, blank-type default that fails validation until filled', () => {
    // The form starts invalid (submit disabled) — date defaults to today only.
    expect(supplierPaymentSchema.safeParse(defaultSupplierPaymentFormValues).success).toBe(false);
  });
});

describe('toCreateBody', () => {
  it('maps validated values to the request body, fixing currency to USD', () => {
    expect(toCreateBody(valid)).toEqual({
      swift_ref: 'SWIFT-123',
      payment_date: '2026-06-01',
      amount: '8000.00',
      currency: 'USD',
      payment_type: 'partial',
      bank_name: 'HSBC',
      notes: 'deposit wire',
    });
  });

  it('omits blank optional fields rather than sending empty strings', () => {
    const body = toCreateBody({ ...valid, bank_name: '', notes: '   ' });
    expect(body.bank_name).toBeUndefined();
    expect(body.notes).toBeUndefined();
  });

  it('trims the swift_ref and amount', () => {
    const body = toCreateBody({ ...valid, swift_ref: '  REF  ', amount: ' 50.00 ' });
    expect(body.swift_ref).toBe('REF');
    expect(body.amount).toBe('50.00');
  });

  it('never sends a status (server-set) or a non-USD currency', () => {
    const body = toCreateBody(valid) as unknown as Record<string, unknown>;
    expect(body.status).toBeUndefined();
    expect(body.currency).toBe('USD');
  });
});
