'use client';

interface Activity {
  id: string;
  agent_id: string;
  type: string;
  title: string;
  description: string;
  timestamp: string;
}

interface Agent {
  id: string;
  name: string;
  color: string;
}

interface ActivityLogProps {
  activities: Activity[];
  selectedAgent: string | null;
  agents: Agent[];
}

const AGENT_NAMES: Record<string, string> = {
  main: 'Kublai',
  researcher: 'Möngke',
  writer: 'Chagatai',
  developer: 'Temüjin',
  analyst: 'Jochi',
  ops: 'Ögedei',
};

const AGENT_COLORS: Record<string, string> = {
  main: '#FFD700',
  researcher: '#4A90D9',
  writer: '#9B59B6',
  developer: '#27AE60',
  analyst: '#E74C3C',
  ops: '#F39C12',
};

const TYPE_ICONS: Record<string, string> = {
  task_created: '📋',
  task_claimed: '👋',
  task_completed: '✅',
  task_blocked: '⚠️',
  knowledge_stored: '🧠',
  collaboration: '🤝',
  notification: '🔔',
  heartbeat: '💓',
  status_change: '🔄',
  delegation: '📤',
  default: '📌',
};

export function ActivityLog({ activities, selectedAgent, agents }: ActivityLogProps) {
  const filteredActivities = selectedAgent
    ? activities.filter(a => a.agent_id === selectedAgent)
    : activities;

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Activity Log
        </h3>
        {selectedAgent && (
          <span className="text-xs px-2 py-1 rounded-full bg-amber-500/20 text-amber-400">
            {AGENT_NAMES[selectedAgent]}
          </span>
        )}
      </div>

      <div className="space-y-2 max-h-80 overflow-y-auto">
        {filteredActivities.slice(0, 50).map((activity, index) => {
          const agentColor = AGENT_COLORS[activity.agent_id] || '#64748b';
          const icon = TYPE_ICONS[activity.type] || TYPE_ICONS.default;

          return (
            <div
              key={activity.id}
              className="flex items-start gap-3 p-2 rounded-lg hover:bg-slate-700/30 transition-colors"
            >
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: `${agentColor}20` }}
              >
                <span className="text-lg">{icon}</span>
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className="text-xs font-medium"
                    style={{ color: agentColor }}
                  >
                    {AGENT_NAMES[activity.agent_id] || activity.agent_id}
                  </span>
                  <span className="text-xs text-slate-500">{formatTime(activity.timestamp)}</span>
                </div>
                <p className="text-sm text-slate-200 line-clamp-1">{activity.title}</p>
                <p className="text-xs text-slate-400 line-clamp-1">{activity.description}</p>
              </div>
            </div>
          );
        })}

        {filteredActivities.length === 0 && (
          <div className="text-center py-8 text-slate-500">
            <svg className="w-10 h-10 mx-auto mb-2 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm">No recent activity</p>
          </div>
        )}
      </div>
    </div>
  );
}
