import { EMPTY_MONEY, formatMoney, parseRatio } from './money';

describe('formatMoney', () => {
  it('formats a GBP string with the £ symbol and two decimals', () => {
    expect(formatMoney('1000.5', 'GBP')).toBe('£1,000.50');
    expect(formatMoney('1000.50', 'GBP')).toBe('£1,000.50');
    expect(formatMoney('0', 'GBP')).toBe('£0.00');
  });

  it('groups thousands without parsing to float (exact digits preserved)', () => {
    expect(formatMoney('1234567.89', 'GBP')).toBe('£1,234,567.89');
    // A value beyond float precision keeps its exact digits.
    expect(formatMoney('12345678901234567.89', 'GBP')).toBe('£12,345,678,901,234,567.89');
  });

  it('accepts numbers (the aggregate endpoint returns numbers, not strings)', () => {
    expect(formatMoney(8000, 'GBP')).toBe('£8,000.00');
    expect(formatMoney(0, 'GBP')).toBe('£0.00');
  });

  it('handles a signed (negative) value, e.g. variance', () => {
    expect(formatMoney('-5.5', 'GBP')).toBe('-£5.50');
    expect(formatMoney(-5.5, 'GBP')).toBe('-£5.50');
  });

  it('maps known currencies and falls back to a prefixed code', () => {
    expect(formatMoney('10', 'USD')).toBe('$10.00');
    expect(formatMoney('10', 'EUR')).toBe('€10.00');
    expect(formatMoney('10', 'ZZZ')).toBe('ZZZ 10.00');
  });

  it('defaults the currency to GBP', () => {
    expect(formatMoney('10')).toBe('£10.00');
  });

  it('renders null / undefined / empty as the masked placeholder', () => {
    expect(formatMoney(null, 'GBP')).toBe(EMPTY_MONEY);
    expect(formatMoney(undefined, 'GBP')).toBe(EMPTY_MONEY);
    expect(formatMoney('', 'GBP')).toBe(EMPTY_MONEY);
  });
});

describe('parseRatio', () => {
  it('returns the clamped 0..1 fraction of part over whole', () => {
    expect(parseRatio('50', '100')).toBeCloseTo(0.5);
    expect(parseRatio(8000, 8000)).toBe(1);
    expect(parseRatio('150', '100')).toBe(1); // clamped
    expect(parseRatio('0', '100')).toBe(0);
  });

  it('returns null when the denominator is missing or zero', () => {
    expect(parseRatio('50', null)).toBeNull();
    expect(parseRatio('50', undefined)).toBeNull();
    expect(parseRatio('50', '0')).toBeNull();
    expect(parseRatio('50', 0)).toBeNull();
  });

  it('returns null when the numerator is missing', () => {
    expect(parseRatio(null, '100')).toBeNull();
    expect(parseRatio(undefined, '100')).toBeNull();
  });
});
