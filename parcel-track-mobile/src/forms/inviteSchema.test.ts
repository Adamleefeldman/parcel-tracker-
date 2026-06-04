import {
  defaultInviteFormValues,
  inviteSchema,
  toCreateBody,
  type InviteFormValues,
} from './inviteSchema';

function validValues(overrides: Partial<InviteFormValues> = {}): InviteFormValues {
  return { email: 'agent@example.com', role: 'uk_agent', ...overrides };
}

describe('inviteSchema', () => {
  it('accepts a valid email + role', () => {
    expect(inviteSchema.safeParse(validValues()).success).toBe(true);
  });

  it('rejects a bad email', () => {
    expect(inviteSchema.safeParse(validValues({ email: 'not-an-email' })).success).toBe(false);
    expect(inviteSchema.safeParse(validValues({ email: '' })).success).toBe(false);
  });

  it('rejects a blank or unknown role', () => {
    expect(inviteSchema.safeParse(validValues({ role: '' })).success).toBe(false);
    expect(inviteSchema.safeParse(validValues({ role: 'superuser' })).success).toBe(false);
  });

  it('accepts every known role', () => {
    for (const role of ['admin', 'morocco_agent', 'uk_agent', 'customer']) {
      expect(inviteSchema.safeParse(validValues({ role })).success).toBe(true);
    }
  });

  it('the shipped defaults are invalid until email + role are filled', () => {
    expect(inviteSchema.safeParse(defaultInviteFormValues).success).toBe(false);
  });
});

describe('toCreateBody', () => {
  it('trims + lowercases the email and passes role through', () => {
    expect(toCreateBody(validValues({ email: '  Agent@Example.com  ' }))).toEqual({
      email: 'agent@example.com',
      role: 'uk_agent',
    });
  });

  it('never includes a booking_id (org-level invite)', () => {
    const body = toCreateBody(validValues());
    expect(JSON.parse(JSON.stringify(body))).not.toHaveProperty('booking_id');
  });
});
