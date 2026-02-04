'use client';

interface MemoryStatsProps {
  stats: {
    research_count: number;
    content_count: number;
    analysis_count: number;
    application_count: number;
    insight_count: number;
    concept_count: number;
    task_count: number;
    notification_count: number;
  } | null;
}

const MEMORY_TYPES = [
  { key: 'research_count', label: 'Research', color: '#4A90D9', icon: '🔍' },
  { key: 'content_count', label: 'Content', color: '#9B59B6', icon: '📝' },
  { key: 'analysis_count', label: 'Analysis', color: '#E74C3C', icon: '📊' },
  { key: 'application_count', label: 'Applications', color: '#27AE60', icon: '⚙️' },
  { key: 'insight_count', label: 'Insights', color: '#F39C12', icon: '💡' },
  { key: 'concept_count', label: 'Concepts', color: '#1ABC9C', icon: '🧠' },
];

export function MemoryStats({ stats }: MemoryStatsProps) {
  if (!stats) {
    return (
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
          </svg>
          Memory Stats
        </h3>
        <div className="text-center py-8 text-slate-500">
          <p>No data available</p>
        </div>
      </div>
    );
  }

  const totalKnowledge = MEMORY_TYPES.reduce((sum, type) => {
    return sum + (stats[type.key as keyof typeof stats] as number || 0);
  }, 0);

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
        </svg>
        Memory Stats
      </h3>

      <div className="space-y-3">
        {MEMORY_TYPES.map(type => {
          const count = stats[type.key as keyof typeof stats] as number || 0;
          const percentage = totalKnowledge > 0 ? (count / totalKnowledge) * 100 : 0;

          return (
            <div key={type.key} className="group">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span>{type.icon}</span>
                  <span className="text-sm text-slate-300">{type.label}</span>
                </div>
                <span className="text-sm font-mono text-slate-400">{count.toLocaleString()}</span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${percentage}%`,
                    backgroundColor: type.color,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-4 border-t border-slate-700">
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-slate-900/50 rounded-lg p-2 text-center">
            <p className="text-xl font-bold text-white">{stats.task_count.toLocaleString()}</p>
            <p className="text-xs text-slate-500">Total Tasks</p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-2 text-center">
            <p className="text-xl font-bold text-white">{stats.notification_count.toLocaleString()}</p>
            <p className="text-xs text-slate-500">Notifications</p>
          </div>
        </div>
      </div>

      <div className="mt-3 text-center">
        <p className="text-xs text-slate-500">
          Total Knowledge Nodes: <span className="text-slate-300 font-mono">{totalKnowledge.toLocaleString()}</span>
        </p>
      </div>
    </div>
  );
}
