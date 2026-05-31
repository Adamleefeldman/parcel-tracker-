import { buildNotificationsPath, notificationsQueryKey } from './useNotifications';
import { unreadCountQueryKey } from './useUnreadCount';

describe('notificationsQueryKey', () => {
  it('returns ["notifications", filters] with an empty filters object by default', () => {
    expect(notificationsQueryKey()).toEqual(['notifications', {}]);
  });

  it('includes filters so different filters do not share a cache slot', () => {
    expect(notificationsQueryKey({ unreadOnly: true })).toEqual([
      'notifications',
      { unreadOnly: true },
    ]);
  });

  it('keeps "notifications" as the first element so prefix invalidation works', () => {
    expect(notificationsQueryKey({ limit: 50 })[0]).toBe('notifications');
  });
});

describe('buildNotificationsPath', () => {
  it('returns the bare collection path when no filters are given', () => {
    expect(buildNotificationsPath({})).toBe('/api/v1/notifications');
  });

  it('emits unread_only/limit/offset', () => {
    expect(buildNotificationsPath({ unreadOnly: true, limit: 50, offset: 0 })).toBe(
      '/api/v1/notifications?unread_only=true&limit=50&offset=0',
    );
  });

  it('omits absent filters', () => {
    expect(buildNotificationsPath({ limit: 5 })).toBe('/api/v1/notifications?limit=5');
  });
});

describe('unreadCountQueryKey', () => {
  it('is under the "notifications" prefix so mark-read invalidates the badge too', () => {
    expect(unreadCountQueryKey()).toEqual(['notifications', 'unread-count']);
    expect(unreadCountQueryKey()[0]).toBe('notifications');
  });
});
