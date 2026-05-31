import { NOTIFICATION_LABELS, notificationLabel, notificationTone } from './notificationDisplay';

describe('notification display', () => {
  const types = Object.keys(NOTIFICATION_LABELS);

  it('maps all 15 NotificationType values to a label', () => {
    expect(types).toHaveLength(15);
    types.forEach((t) => expect(typeof NOTIFICATION_LABELS[t as never]).toBe('string'));
  });

  it('returns a valid pill tone for every type', () => {
    const validTones = ['default', 'success', 'warning', 'error'];
    types.forEach((t) => expect(validTones).toContain(notificationTone(t as never)));
  });

  it('falls back gracefully for an unknown type', () => {
    expect(notificationLabel('bogus' as never)).toBe('Notification');
    expect(notificationTone('bogus' as never)).toBe('default');
  });
});
