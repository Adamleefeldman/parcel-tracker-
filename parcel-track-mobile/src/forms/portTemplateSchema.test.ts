import {
  defaultPortTemplateFormValues,
  portTemplateSchema,
  toUpsertBody,
  type PortTemplateFormValues,
} from './portTemplateSchema';

function validValues(overrides: Partial<PortTemplateFormValues> = {}): PortTemplateFormValues {
  return {
    free_days_detention: '5',
    free_days_demurrage: '3',
    detention_rate_gbp_after: '120.00',
    demurrage_rate_gbp_after: '',
    ...overrides,
  };
}

describe('portTemplateSchema', () => {
  it('accepts a valid payload', () => {
    expect(portTemplateSchema.safeParse(validValues()).success).toBe(true);
  });

  it('accepts the shipped defaults (zeros, blank rates)', () => {
    expect(portTemplateSchema.safeParse(defaultPortTemplateFormValues).success).toBe(true);
  });

  it('accepts zero free-days', () => {
    expect(portTemplateSchema.safeParse(validValues({ free_days_detention: '0' })).success).toBe(
      true,
    );
  });

  it('rejects negative free-days', () => {
    expect(portTemplateSchema.safeParse(validValues({ free_days_detention: '-1' })).success).toBe(
      false,
    );
  });

  it('rejects non-integer free-days', () => {
    expect(portTemplateSchema.safeParse(validValues({ free_days_demurrage: '3.5' })).success).toBe(
      false,
    );
    expect(portTemplateSchema.safeParse(validValues({ free_days_demurrage: 'x' })).success).toBe(
      false,
    );
    expect(portTemplateSchema.safeParse(validValues({ free_days_demurrage: '' })).success).toBe(
      false,
    );
  });

  it('accepts a blank (optional) rate', () => {
    expect(
      portTemplateSchema.safeParse(validValues({ detention_rate_gbp_after: '' })).success,
    ).toBe(true);
  });

  it('rejects a negative or malformed rate', () => {
    expect(
      portTemplateSchema.safeParse(validValues({ detention_rate_gbp_after: '-5' })).success,
    ).toBe(false);
    expect(
      portTemplateSchema.safeParse(validValues({ detention_rate_gbp_after: '12.345' })).success,
    ).toBe(false);
    expect(
      portTemplateSchema.safeParse(validValues({ detention_rate_gbp_after: 'abc' })).success,
    ).toBe(false);
  });
});

describe('toUpsertBody', () => {
  it('converts free-days to numbers and keeps rates as strings', () => {
    const body = toUpsertBody(validValues());
    expect(body.free_days_detention).toBe(5);
    expect(typeof body.free_days_detention).toBe('number');
    expect(body.detention_rate_gbp_after).toBe('120.00');
    expect(typeof body.detention_rate_gbp_after).toBe('string');
  });

  it('omits a blank rate from the body', () => {
    const body = toUpsertBody(validValues({ demurrage_rate_gbp_after: '' }));
    expect(body.demurrage_rate_gbp_after).toBeUndefined();
    const wire = JSON.parse(JSON.stringify(body));
    expect(wire).not.toHaveProperty('demurrage_rate_gbp_after');
  });

  it('never parseFloats a rate (exact string survives)', () => {
    const body = toUpsertBody(validValues({ detention_rate_gbp_after: '0.10' }));
    expect(body.detention_rate_gbp_after).toBe('0.10');
  });
});
