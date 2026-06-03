import {
  companySchema,
  defaultCompanyFormValues,
  parseAliases,
  toCreateBody,
  type CompanyFormValues,
} from './companySchema';

function validValues(overrides: Partial<CompanyFormValues> = {}): CompanyFormValues {
  return {
    legal_name: 'Acme Foods Ltd',
    aliases: '',
    registration_no: '',
    vat_no: '',
    default_address: '',
    ...overrides,
  };
}

describe('companySchema', () => {
  it('accepts a valid payload (legal_name only)', () => {
    expect(companySchema.safeParse(validValues()).success).toBe(true);
  });

  it('requires a non-empty legal_name', () => {
    expect(companySchema.safeParse(validValues({ legal_name: '' })).success).toBe(false);
    expect(companySchema.safeParse(validValues({ legal_name: '   ' })).success).toBe(false);
  });

  it('the shipped defaults are invalid until legal_name is filled', () => {
    expect(companySchema.safeParse(defaultCompanyFormValues).success).toBe(false);
  });
});

describe('parseAliases', () => {
  it('splits on comma, trims, and drops blanks', () => {
    expect(parseAliases('Acme, Acme UK, Acme Foods')).toEqual(['Acme', 'Acme UK', 'Acme Foods']);
    expect(parseAliases('Acme, , Acme UK,')).toEqual(['Acme', 'Acme UK']);
  });

  it('returns an empty array for a blank string', () => {
    expect(parseAliases('')).toEqual([]);
    expect(parseAliases('  ,  , ')).toEqual([]);
  });
});

describe('toCreateBody', () => {
  it('maps aliases to a string[] and omits blank optionals', () => {
    const body = toCreateBody(
      validValues({ aliases: 'Acme, Acme UK', vat_no: 'GB123', registration_no: '' }),
    );
    expect(body.legal_name).toBe('Acme Foods Ltd');
    expect(body.aliases).toEqual(['Acme', 'Acme UK']);
    expect(body.vat_no).toBe('GB123');
    expect(body.registration_no).toBeUndefined();

    // Blank optionals + empty aliases are dropped from the wire entirely.
    const wire = JSON.parse(JSON.stringify(body));
    expect(wire).not.toHaveProperty('registration_no');
    expect(wire).not.toHaveProperty('default_address');
  });

  it('omits aliases entirely when the field is blank (not an empty array)', () => {
    const body = toCreateBody(validValues({ aliases: '' }));
    expect(body.aliases).toBeUndefined();
    const wire = JSON.parse(JSON.stringify(body));
    expect(wire).not.toHaveProperty('aliases');
  });

  it('trims the legal_name', () => {
    expect(toCreateBody(validValues({ legal_name: '  Acme  ' })).legal_name).toBe('Acme');
  });
});
