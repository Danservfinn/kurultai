'use client';

interface Notification {
  id: string;
  type: 'task_complete' | 'task_blocked' | 'insight';
  task_id: string;
  from_agent: string;
  summary: string;
  created_at: string;
  read: boolean;
}

interface NotificationCenterProps {
  notifications: Notification[];
  unreadCount: number;
}

const AGENT_NAMES: Record<string, string> = {
  main: 'Kublai',
  researcher: 'Möngke',
  writer: 'Chagatai',
  developer: 'Temüjin',
  analyst: 'Jochi',
  ops: 'Ögedei',
};

const TYPE_ICONS: Record<string, string> = {
  task_complete: '✓',
  task_blocked: '⚠️',
  insight: '💡',
};

const TYPE_COLORS: Record<string, string> = {
  task_complete: 'text-green-400 bg-green-500/10',
  task_blocked: 'text-red-400 bg-red-500/10',
  insight: 'text-amber-400 bg-amber-500/10',
};

export function NotificationCenter({ notifications, unreadCount }: NotificationCenterProps) {
  const sortedNotifications = [...notifications].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          Notifications
        </h3>
        {unreadCount > 0 && (
          <span className="bg-red-500 text-white text-xs px-2 py-1 rounded-full">
            {unreadCount} unread
          </span>
        )}
      </div>

      <div className="space-y-2 max-h-80 overflow-y-auto">
        {sortedNotifications.slice(0, 20).map(notification => (
          <div
            key={notification.id}
            className={`
              p-3 rounded-lg border transition-colors
              ${notification.read
                ? 'border-slate-700 bg-slate-800/30'
                : 'border-amber-500/50 bg-amber-500/5'
              }
            `}
          >
            <div className="flex items-start gap-3">
              <span className={`w-8 h-8 rounded-lg flex items-center justify-center text-lg ${TYPE_COLORS[notification.type]}`}>
                {TYPE_ICONS[notification.type]}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-200 line-clamp-2">{notification.summary}</p>
                <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                  <span>From: {AGENT_NAMES[notification.from_agent] || notification.from_agent}</span>
                  <span>•</span>
                  <span>{new Date(notification.created_at).toLocaleTimeString()}</span>
                </div>
              </div>
              {!notification.read && (
                <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0" />
              )}
            </div>
          </div>
        ))}

        {sortedNotifications.length === 0 && (
          <div className="text-center py-8 text-slate-500">
            <svg className="w-12 h-12 mx-auto mb-2 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
            </svg>
            <p>No notifications</p>
          </div>
        )}
      </div>
    </div>
  );
}
