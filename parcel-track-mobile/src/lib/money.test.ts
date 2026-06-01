import { EMPTY_MONEY, formatMoney, parseRatio, sumDecimalStrings } from './money';

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

describe('sumDecimalStrings', () => {
  it('sums two values to the exact cent (no float drift)', () => {
    // The canonical float-drift trap: 0.1 + 0.2 === 0.30000000000000004 in
    // IEEE-754. Integer-cents maths must give exactly "0.30".
    expect(sumDecimalStrings(['0.10', '0.20'])).toBe('0.30');
  });

  it('sums a list of whole and fractional amounts', () => {
    expect(sumDecimalStrings(['8000.00', '2000.50', '0.50'])).toBe('10001.00');
    expect(sumDecimalStrings(['100', '0.01'])).toBe('100.01');
  });

  it('skips null / undefined / empty entries (masked or absent amounts)', () => {
    expect(sumDecimalStrings(['5.00', null, '5.00', undefined, ''])).toBe('10.00');
  });

  it('returns "0.00" for an empty or all-null list', () => {
    expect(sumDecimalStrings([])).toBe('0.00');
    expect(sumDecimalStrings([null, undefined, ''])).toBe('0.00');
  });

  it('normalises single-digit fractional inputs to two decimals', () => {
    expect(sumDecimalStrings(['1.5'])).toBe('1.50');
    expect(sumDecimalStrings(['1.5', '2.5'])).toBe('4.00');
  });

  it('handles many small tranches without accumulating float error', () => {
    expect(sumDecimalStrings(Array(10).fill('0.10'))).toBe('1.00');
  });

  it('handles negative values (sign is preserved)', () => {
    expect(sumDecimalStrings(['10.00', '-2.50'])).toBe('7.50');
    expect(sumDecimalStrings(['-1.00', '-2.00'])).toBe('-3.00');
  });

  it('skips values that are not a clean decimal', () => {
    expect(sumDecimalStrings(['5.00', 'abc', '5.00'])).toBe('10.00');
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
