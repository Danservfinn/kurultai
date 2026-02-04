'use client';

import { useState } from 'react';

interface Task {
  id: string;
  type: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' | 'escalated';
  assigned_to: string;
  delegated_by: string;
  quality_score?: number;
  blocked_reason?: string;
  escalation_count?: number;
  created_at: string;
  completed_at?: string;
}

interface TaskBoardProps {
  pending: Task[];
  inProgress: Task[];
  completed: Task[];
  blocked: Task[];
  selectedAgent: string | null;
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

export function TaskBoard({ pending, inProgress, completed, blocked, selectedAgent }: TaskBoardProps) {
  const [filter, setFilter] = useState<'all' | 'mine'>('all');

  const filterTasks = (tasks: Task[]) => {
    if (filter === 'all') return tasks;
    if (!selectedAgent) return tasks;
    return tasks.filter(t => t.assigned_to === selectedAgent || t.delegated_by === selectedAgent);
  };

  const columns = [
    {
      title: 'Pending',
      tasks: filterTasks(pending),
      color: 'border-slate-500',
      bgColor: 'bg-slate-500/10',
    },
    {
      title: 'In Progress',
      tasks: filterTasks(inProgress),
      color: 'border-blue-500',
      bgColor: 'bg-blue-500/10',
    },
    {
      title: 'Blocked/Escalated',
      tasks: filterTasks(blocked),
      color: 'border-red-500',
      bgColor: 'bg-red-500/10',
    },
    {
      title: 'Completed',
      tasks: filterTasks(completed),
      color: 'border-green-500',
      bgColor: 'bg-green-500/10',
    },
  ];

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
          Task Board
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1 rounded-lg text-sm transition-colors ${
              filter === 'all' ? 'bg-amber-500 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilter('mine')}
            disabled={!selectedAgent}
            className={`px-3 py-1 rounded-lg text-sm transition-colors ${
              filter === 'mine'
                ? 'bg-amber-500 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed'
            }`}
          >
            Selected Agent
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {columns.map(column => (
          <div key={column.title} className={`rounded-lg border-t-4 ${column.color} bg-slate-900/50 p-3`}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-slate-300">{column.title}</h4>
              <span className={`text-xs px-2 py-0.5 rounded-full ${column.bgColor} text-white`}>
                {column.tasks.length}
              </span>
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto">
              {column.tasks.map(task => (
                <div
                  key={task.id}
                  className={`
                    p-3 rounded-lg border border-slate-700 bg-slate-800/50
                    hover:border-slate-600 transition-colors
                    ${selectedAgent && (task.assigned_to === selectedAgent || task.delegated_by === selectedAgent)
                      ? 'ring-1 ring-amber-500/50'
                      : ''
                    }
                  `}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <span className="text-xs font-mono text-slate-500">#{task.id.slice(0, 8)}</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-300">
                      {task.type}
                    </span>
                  </div>

                  <p className="text-sm text-slate-200 mb-2 line-clamp-2">{task.description}</p>

                  <div className="flex items-center gap-2 text-xs">
                    <span
                      className="px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: `${AGENT_COLORS[task.assigned_to]}20`,
                        color: AGENT_COLORS[task.assigned_to],
                      }}
                    >
                      {AGENT_NAMES[task.assigned_to] || task.assigned_to}
                    </span>
                    <span className="text-slate-500">←</span>
                    <span className="text-slate-400">{AGENT_NAMES[task.delegated_by] || task.delegated_by}</span>
                  </div>

                  {task.blocked_reason && (
                    <p className="mt-2 text-xs text-red-400 bg-red-500/10 p-2 rounded">
                      ⚠️ {task.blocked_reason}
                    </p>
                  )}

                  {task.escalation_count && task.escalation_count > 0 && (
                    <p className="mt-2 text-xs text-amber-400">
                      Escalated {task.escalation_count}x
                    </p>
                  )}

                  {task.quality_score && (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-green-500 rounded-full"
                          style={{ width: `${task.quality_score * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-slate-400">{Math.round(task.quality_score * 100)}%</span>
                    </div>
                  )}
                </div>
              ))}

              {column.tasks.length === 0 && (
                <div className="text-center py-4 text-slate-500 text-sm">
                  No tasks
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
