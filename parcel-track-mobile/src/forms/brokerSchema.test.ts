import {
  brokerSchema,
  defaultBrokerFormValues,
  toCreateBody,
  type BrokerFormValues,
} from './brokerSchema';

function validValues(overrides: Partial<BrokerFormValues> = {}): BrokerFormValues {
  return { code: 'BRK-UK-01', name: 'Acme Brokers', phone: '', ...overrides };
}

describe('brokerSchema', () => {
  it('accepts a valid payload (phone optional)', () => {
    expect(brokerSchema.safeParse(validValues()).success).toBe(true);
  });

  it('requires non-empty code and name', () => {
    expect(brokerSchema.safeParse(validValues({ code: '' })).success).toBe(false);
    expect(brokerSchema.safeParse(validValues({ name: '   ' })).success).toBe(false);
  });

  it('the shipped defaults are invalid until code + name are filled', () => {
    expect(brokerSchema.safeParse(defaultBrokerFormValues).success).toBe(false);
  });
});

describe('toCreateBody', () => {
  it('trims fields and omits a blank phone', () => {
    const body = toCreateBody(validValues({ code: ' BRK ', name: ' Acme ', phone: '' }));
    expect(body).toEqual({ code: 'BRK', name: 'Acme' });
    expect(JSON.parse(JSON.stringify(body))).not.toHaveProperty('phone');
  });

  it('keeps a non-blank phone', () => {
    expect(toCreateBody(validValues({ phone: '+44 20 1234' })).phone).toBe('+44 20 1234');
  });
});
