'use client';

import { useMemo } from 'react';

interface Agent {
  id: string;
  name: string;
  role: string;
  color: string;
  capabilities: string[];
  personality: string;
  status?: string;
  lastActive?: string;
}

interface AgentStatusCardProps {
  agent: Agent;
  isSelected: boolean;
  onClick: () => void;
  taskCount: number;
}

export function AgentStatusCard({ agent, isSelected, onClick, taskCount }: AgentStatusCardProps) {
  const status = agent.status || 'idle';

  const statusColor = useMemo(() => {
    switch (status) {
      case 'active':
      case 'working':
        return 'bg-green-500';
      case 'idle':
        return 'bg-slate-500';
      case 'error':
      case 'blocked':
        return 'bg-red-500';
      case 'delegating':
        return 'bg-amber-500';
      default:
        return 'bg-slate-500';
    }
  }, [status]);

  const isAlive = agent.lastActive
    ? new Date().getTime() - new Date(agent.lastActive).getTime() < 5 * 60 * 1000
    : false;

  return (
    <button
      onClick={onClick}
      className={`
        relative p-4 rounded-xl border-2 transition-all duration-200 text-left w-full
        ${isSelected
          ? 'border-amber-500 bg-amber-500/10 shadow-lg shadow-amber-500/20'
          : 'border-slate-700 bg-slate-800/50 hover:border-slate-600 hover:bg-slate-800'
        }
      `}
    >
      {/* Status Indicator */}
      <div className="absolute top-3 right-3 flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${statusColor} ${isAlive ? 'animate-pulse' : ''}`} />
        {taskCount > 0 && (
          <span className="text-xs font-mono bg-slate-700 px-2 py-0.5 rounded-full text-slate-300">
            {taskCount}
          </span>
        )}
      </div>

      {/* Agent Icon */}
      <div
        className="w-12 h-12 rounded-xl flex items-center justify-center mb-3"
        style={{ backgroundColor: `${agent.color}20`, border: `2px solid ${agent.color}40` }}
      >
        <span className="text-xl font-bold" style={{ color: agent.color }}>
          {agent.name[0]}
        </span>
      </div>

      {/* Agent Info */}
      <h3 className="font-semibold text-white mb-1">{agent.name}</h3>
      <p className="text-xs text-slate-400 mb-2 line-clamp-1">{agent.role}</p>

      {/* Status Badge */}
      <div className="flex items-center gap-2">
        <span className={`
          text-xs px-2 py-1 rounded-full font-medium capitalize
          ${status === 'active' || status === 'working'
            ? 'bg-green-500/20 text-green-400'
            : status === 'error' || status === 'blocked'
              ? 'bg-red-500/20 text-red-400'
              : 'bg-slate-700/50 text-slate-400'
          }
        `}>
          {status}
        </span>
        {!isAlive && agent.lastActive && (
          <span className="text-xs text-slate-500">
            {new Date(agent.lastActive).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>

      {/* Capabilities (shown when selected) */}
      {isSelected && (
        <div className="mt-3 pt-3 border-t border-slate-700">
          <p className="text-xs text-slate-500 mb-2">Capabilities</p>
          <div className="flex flex-wrap gap-1">
            {agent.capabilities.slice(0, 3).map(cap => (
              <span key={cap} className="text-xs bg-slate-700/50 px-2 py-0.5 rounded text-slate-300">
                {cap}
              </span>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-2 italic line-clamp-2">{agent.personality}</p>
        </div>
      )}
    </button>
  );
}
