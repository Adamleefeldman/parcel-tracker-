import { DOCUMENT_ENTITY_LABELS } from './enums';

describe('DOCUMENT_ENTITY_LABELS', () => {
  const keys = Object.keys(DOCUMENT_ENTITY_LABELS);

  it('maps all 6 DocumentEntityType values to a label', () => {
    expect([...keys].sort()).toEqual(
      [
        'purchase_order',
        'invoice',
        'payment',
        'bill_of_lading',
        'clearing_docs',
        'delivery_schedule',
      ].sort(),
    );
  });

  it('gives every entity a non-empty label', () => {
    keys.forEach((k) => {
      expect(typeof DOCUMENT_ENTITY_LABELS[k as never]).toBe('string');
      expect((DOCUMENT_ENTITY_LABELS[k as never] as string).length).toBeGreaterThan(0);
    });
  });
});
