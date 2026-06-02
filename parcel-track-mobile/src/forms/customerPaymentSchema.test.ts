import {
  customerPaymentSchema,
  defaultPaymentFormValues,
  toCreateBody,
  type CustomerPaymentFormValues,
} from './customerPaymentSchema';

function validValues(
  overrides: Partial<CustomerPaymentFormValues> = {},
): CustomerPaymentFormValues {
  return {
    payment_date: '2026-04-15',
    method: 'transfer',
    amount_received: '8000.00',
    variance: '',
    expense_courier: '',
    expense_bank_charge: '',
    banked_total: '8000.00',
    sender_bank: 'Barclays',
    receiver_bank: 'HSBC',
    tranche_index: '1',
    customer_invoice_ref: '',
    notes: '',
    ...overrides,
  };
}

describe('customerPaymentSchema', () => {
  it('accepts a valid payload', () => {
    expect(customerPaymentSchema.safeParse(validValues()).success).toBe(true);
  });

  it('rejects amount_received of zero', () => {
    expect(customerPaymentSchema.safeParse(validValues({ amount_received: '0' })).success).toBe(
      false,
    );
    expect(customerPaymentSchema.safeParse(validValues({ amount_received: '0.00' })).success).toBe(
      false,
    );
  });

  it('rejects a non-decimal / malformed amount', () => {
    expect(customerPaymentSchema.safeParse(validValues({ amount_received: 'abc' })).success).toBe(
      false,
    );
    // More than two fractional digits is not allowed.
    expect(
      customerPaymentSchema.safeParse(validValues({ amount_received: '10.123' })).success,
    ).toBe(false);
    // A negative amount is not allowed (only variance is signed).
    expect(customerPaymentSchema.safeParse(validValues({ amount_received: '-5' })).success).toBe(
      false,
    );
  });

  it('rejects a missing method', () => {
    expect(customerPaymentSchema.safeParse(validValues({ method: '' })).success).toBe(false);
    expect(customerPaymentSchema.safeParse(validValues({ method: 'cheque' })).success).toBe(false);
  });

  it('rejects a bad payment_date', () => {
    expect(
      customerPaymentSchema.safeParse(validValues({ payment_date: '15/04/2026' })).success,
    ).toBe(false);
    expect(customerPaymentSchema.safeParse(validValues({ payment_date: '' })).success).toBe(false);
  });

  it('rejects tranche_index below 1', () => {
    expect(customerPaymentSchema.safeParse(validValues({ tranche_index: '0' })).success).toBe(
      false,
    );
    expect(customerPaymentSchema.safeParse(validValues({ tranche_index: 'x' })).success).toBe(
      false,
    );
  });

  it('rejects negative expenses', () => {
    expect(customerPaymentSchema.safeParse(validValues({ expense_courier: '-1' })).success).toBe(
      false,
    );
    expect(
      customerPaymentSchema.safeParse(validValues({ expense_bank_charge: '-0.01' })).success,
    ).toBe(false);
  });

  it('accepts a signed variance (negative = short, positive = over)', () => {
    expect(customerPaymentSchema.safeParse(validValues({ variance: '-50.25' })).success).toBe(true);
    expect(customerPaymentSchema.safeParse(validValues({ variance: '50.25' })).success).toBe(true);
  });

  it('accepts blank optional decimals', () => {
    expect(
      customerPaymentSchema.safeParse(
        validValues({ variance: '', expense_courier: '', banked_total: '' }),
      ).success,
    ).toBe(true);
  });

  it('validates the shipped default values (today + tranche 1, but method blank)', () => {
    // The form opens with a blank method, so the defaults alone are invalid
    // until the user picks one — which is why the submit button starts disabled.
    expect(customerPaymentSchema.safeParse(defaultPaymentFormValues).success).toBe(false);
    expect(
      customerPaymentSchema.safeParse({
        ...defaultPaymentFormValues,
        method: 'cash',
        amount_received: '1',
      }).success,
    ).toBe(true);
  });
});

describe('toCreateBody', () => {
  it('keeps money as strings and omits blank optional fields', () => {
    const body = toCreateBody(
      validValues({ variance: '', expense_courier: '', customer_invoice_ref: '' }),
    );
    expect(body.amount_received).toBe('8000.00');
    expect(typeof body.amount_received).toBe('string');
    expect(body.banked_total).toBe('8000.00');
    expect(body.variance).toBeUndefined();
    expect(body.expense_courier).toBeUndefined();
    expect(body.customer_invoice_ref).toBeUndefined();
    // Blank optionals are undefined → JSON.stringify drops them from the wire.
    const wire = JSON.parse(JSON.stringify(body));
    expect(wire).not.toHaveProperty('variance');
    expect(wire).not.toHaveProperty('expense_courier');
    expect(wire).not.toHaveProperty('customer_invoice_ref');
  });

  it('converts tranche_index (a count, not money) to a number', () => {
    const body = toCreateBody(validValues({ tranche_index: '3' }));
    expect(body.tranche_index).toBe(3);
    expect(typeof body.tranche_index).toBe('number');
  });

  it('drops bank fields when the method is not a transfer', () => {
    const body = toCreateBody(
      validValues({ method: 'cash', sender_bank: 'Barclays', receiver_bank: 'HSBC' }),
    );
    expect(body.sender_bank).toBeUndefined();
    expect(body.receiver_bank).toBeUndefined();
  });

  it('keeps bank fields for a transfer', () => {
    const body = toCreateBody(validValues({ method: 'transfer', sender_bank: 'Barclays' }));
    expect(body.sender_bank).toBe('Barclays');
  });

  it('never emits a float for amount_received', () => {
    const body = toCreateBody(validValues({ amount_received: '1000.10' }));
    expect(body.amount_received).toBe('1000.10');
  });
});
