import type { ARAgingBucket } from '../../api/types/moneyRisk';
import {
  agedExposure,
  arBucketTone,
  demurrageTone,
  disputesTone,
  formatDaysRemaining,
} from './moneyRiskFormat';

describe('formatDaysRemaining (whole days — no fabricated hours)', () => {
  it('renders a positive count as "Nd"', () => {
    expect(formatDaysRemaining(2)).toBe('2d');
    expect(formatDaysRemaining(7)).toBe('7d');
  });

  it('renders zero as "Today"', () => {
    expect(formatDaysRemaining(0)).toBe('Today');
  });

  it('renders a negative count as "Expired"', () => {
    expect(formatDaysRemaining(-1)).toBe('Expired');
    expect(formatDaysRemaining(-5)).toBe('Expired');
  });
});

describe('demurrageTone', () => {
  it('is error when expired or out of free time', () => {
    expect(demurrageTone({ days_remaining: -1, expired: true })).toBe('error');
    expect(demurrageTone({ days_remaining: 0, expired: false })).toBe('error');
  });

  it('is warning within the warning lead window', () => {
    expect(demurrageTone({ days_remaining: 2, expired: false })).toBe('warning');
    expect(demurrageTone({ days_remaining: 3, expired: false })).toBe('warning');
  });

  it('is default when comfortably ahead of expiry', () => {
    expect(demurrageTone({ days_remaining: 7, expired: false })).toBe('default');
  });
});

describe('arBucketTone', () => {
  it('flags the 60+ band as error and 31-60 as warning', () => {
    expect(arBucketTone('60+')).toBe('error');
    expect(arBucketTone('31-60')).toBe('warning');
  });

  it('leaves the fresh bands neutral', () => {
    expect(arBucketTone('0-14')).toBe('default');
    expect(arBucketTone('15-30')).toBe('default');
  });
});

describe('agedExposure (30+ days, summed exactly)', () => {
  const buckets: ARAgingBucket[] = [
    { label: '0-14', count: 3, amount: '17880.00' },
    { label: '15-30', count: 2, amount: '5880.00' },
    { label: '31-60', count: 4, amount: '11820.00' },
    { label: '60+', count: 2, amount: '6600.00' },
  ];

  it('sums the 31-60 and 60+ bands only', () => {
    expect(agedExposure(buckets)).toEqual({ amount: '18420.00', count: 6 });
  });

  it('is 0.00 / 0 when there is nothing aged', () => {
    expect(agedExposure([buckets[0], buckets[1]])).toEqual({ amount: '0.00', count: 0 });
  });

  it('sums in cents without float drift', () => {
    expect(
      agedExposure([
        { label: '31-60', count: 1, amount: '0.10' },
        { label: '60+', count: 1, amount: '0.20' },
      ]),
    ).toEqual({ amount: '0.30', count: 2 });
  });
});

describe('disputesTone', () => {
  it('is warning when anything is unacknowledged, success when clear', () => {
    expect(disputesTone(2)).toBe('warning');
    expect(disputesTone(0)).toBe('success');
  });
});
