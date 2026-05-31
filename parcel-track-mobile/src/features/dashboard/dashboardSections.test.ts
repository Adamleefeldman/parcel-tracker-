import { dashboardConfig } from './dashboardSections';

describe('dashboardConfig', () => {
  it('admin sees all 8 statuses', () => {
    const config = dashboardConfig('admin');
    expect(config.greeting).toBe('Admin');
    expect(config.emphasizedStatuses).toHaveLength(8);
  });

  it('morocco_agent emphasizes origin / pre-shipment statuses', () => {
    expect(dashboardConfig('morocco_agent').emphasizedStatuses).toEqual([
      'draft',
      'po_submitted',
      'invoice_received',
      'payment_confirmed',
      'bl_issued',
    ]);
  });

  it('uk_agent emphasizes transit + clearance statuses', () => {
    expect(dashboardConfig('uk_agent').emphasizedStatuses).toEqual(['in_transit', 'cleared']);
  });

  it('customer emphasizes shipment / payment-facing statuses', () => {
    expect(dashboardConfig('customer').emphasizedStatuses).toEqual([
      'in_transit',
      'cleared',
      'complete',
    ]);
  });

  it('falls back without throwing for an undefined role', () => {
    const config = dashboardConfig(undefined);
    expect(config.emphasizedStatuses.length).toBeGreaterThan(0);
    expect(typeof config.greeting).toBe('string');
  });
});
