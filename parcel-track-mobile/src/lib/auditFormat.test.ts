import { humanizeAction, prettyJson } from './auditFormat';

describe('humanizeAction', () => {
  it('turns a dotted/underscored action code into a sentence', () => {
    expect(humanizeAction('booking.status_changed')).toBe('Booking status changed');
    expect(humanizeAction('container.dispute_opened')).toBe('Container dispute opened');
    expect(humanizeAction('container.dispute_acknowledged')).toBe('Container dispute acknowledged');
    expect(humanizeAction('shipment_leg.created')).toBe('Shipment leg created');
  });

  it('capitalises only the first word', () => {
    expect(humanizeAction('foo.bar')).toBe('Foo bar');
  });

  it('echoes empty input back unchanged', () => {
    expect(humanizeAction('')).toBe('');
  });
});

describe('prettyJson', () => {
  it('re-indents a parseable JSON string', () => {
    expect(prettyJson('{"status": "draft"}')).toBe('{\n  "status": "draft"\n}');
  });

  it('returns the raw string for non-JSON', () => {
    expect(prettyJson('not json')).toBe('not json');
  });

  it('returns null for null/undefined/blank', () => {
    expect(prettyJson(null)).toBeNull();
    expect(prettyJson(undefined)).toBeNull();
    expect(prettyJson('   ')).toBeNull();
  });
});
