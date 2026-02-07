'use client';

/**
 * GoalOrchestrationPanel
 *
 * Multi-goal orchestration UI for Kublai's agent system.
 * Demonstrates UX patterns for:
 * - Goal detection and synergy visualization
 * - Progress visibility across multiple goals
 * - Agent workload transparency
 * - Mid-course corrections
 *
 * Usage Example:
 * ```tsx
 * <GoalOrchestrationPanel
 *   goals={goals}
 *   agents={agents}
 *   onGoalSelect={handleGoalSelect}
 *   onReprioritize={handleReprioritize}
 *   transparencyMode={userPreferences.transparencyMode}
 * />
 * ```
 */

import React, { useState, useMemo } from 'react';

// ============================================================================
// Types
// ============================================================================

export type TransparencyMode = 'simple' | 'normal' | 'detailed';
export type GoalStatus = 'active' | 'paused' | 'completed' | 'blocked';
export type UpdateFrequency = 'realtime' | 'daily' | 'milestones' | 'headlines';

export interface AgentRef {
  id: string;
  name: string;
  avatar?: string;
  specialization: string[];
  currentTasks: number;
  capacity: number; // 0-100
}

export interface Task {
  id: string;
  title: string;
  assignedAgent: string;
  status: 'pending' | 'in-progress' | 'completed' | 'blocked';
  progress: number; // 0-100
  estimatedCompletion?: Date;
}

export interface Goal {
  id: string;
  title: string;
  description: string;
  progress: number; // 0-100
  status: GoalStatus;
  assignedAgents: AgentRef[];
  tasks: Task[];
  deadline?: Date;
  synergyWith?: string[]; // IDs of related goals
  createdAt: Date;
  priority: 'high' | 'medium' | 'low';
  category?: string; // For grouping
}

export interface SynergyEdge {
  source: string; // Goal ID
  target: string; // Goal ID
  type: 'sequential' | 'synergistic' | 'shared-resource';
  strength: number; // 0-1, how strong the relationship is
}

export interface TimelineEvent {
  id: string;
  timestamp: Date;
  type: 'milestone' | 'task_complete' | 'blocker' | 'decision' | 'agent_handoff';
  goalId: string;
  agent?: AgentRef;
  description: string;
  impact?: string; // Human-readable impact
}

// ============================================================================
// Interfaces
// ============================================================================

interface GoalOrchestrationPanelProps {
  goals: Goal[];
  agents: AgentRef[];
  synergies?: SynergyEdge[];
  timeline?: TimelineEvent[];
  transparencyMode?: TransparencyMode;
  onGoalSelect?: (goalId: string) => void;
  onReprioritize?: (goalIds: string[], priority: 'high' | 'medium' | 'low') => void;
  onPauseGoal?: (goalId: string) => void;
  onResumeGoal?: (goalId: string) => void;
  onRemoveGoal?: (goalId: string) => void;
}

// ============================================================================
// Helper Components
// ============================================================================

/**
 * Progress bar with percentage indicator
 */
const ProgressBar: React.FC<{
  progress: number;
  status: GoalStatus;
  size?: 'sm' | 'md' | 'lg';
}> = ({ progress, status, size = 'md' }) => {
  const heightClasses = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3'
  };

  const statusColors = {
    active: 'bg-blue-500',
    paused: 'bg-yellow-500',
    completed: 'bg-green-500',
    blocked: 'bg-red-500'
  };

  return (
    <div className="relative">
      <div className={`w-full bg-gray-700 rounded-full ${heightClasses[size]}`}>
        <div
          className={`${statusColors[status]} ${heightClasses[size]} rounded-full transition-all duration-500`}
          style={{ width: `${progress}%` }}
        />
      </div>
      {size !== 'sm' && (
        <span className="absolute -top-5 right-0 text-xs text-gray-400">
          {progress}%
        </span>
      )}
    </div>
  );
};

/**
 * Agent avatars with hover details
 */
const AgentAvatars: React.FC<{
  agents: AgentRef[];
  compact?: boolean;
  onAgentClick?: (agentId: string) => void;
}> = ({ agents, compact = false, onAgentClick }) => {
  if (agents.length === 0) return null;

  return (
    <div className={`flex items-center ${compact ? '-space-x-2' : 'gap-2'}`}>
      {agents.map((agent) => (
        <div
          key={agent.id}
          className="relative group"
          onClick={() => onAgentClick?.(agent.id)}
        >
          <div
            className={`
              rounded-full bg-gradient-to-br from-amber-600 to-amber-800
              flex items-center justify-center text-white font-semibold
              cursor-pointer hover:ring-2 hover:ring-amber-400
              transition-all
              ${compact ? 'w-6 h-6 text-xs' : 'w-8 h-8 text-sm'}
            `}
            title={agent.name}
          >
            {agent.name.charAt(0)}
          </div>

          {/* Hover tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-50">
            <div className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs whitespace-nowrap">
              <div className="font-semibold text-amber-400">{agent.name}</div>
              <div className="text-gray-400">{agent.specialization.join(', ')}</div>
              <div className="text-gray-500 mt-1">
                {agent.currentTasks} tasks • {agent.capacity}% capacity
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

/**
 * Status badge with color coding
 */
const StatusBadge: React.FC<{ status: GoalStatus }> = ({ status }) => {
  const badges = {
    active: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    paused: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    completed: 'bg-green-500/20 text-green-400 border-green-500/30',
    blocked: 'bg-red-500/20 text-red-400 border-red-500/30'
  };

  const labels = {
    active: 'ACTIVE',
    paused: 'PAUSED',
    completed: 'DONE',
    blocked: 'BLOCKED'
  };

  return (
    <span className={`px-2 py-1 rounded text-xs font-semibold border ${badges[status]}`}>
      {labels[status]}
    </span>
  );
};

/**
 * Synergy indicator showing related goals
 */
const SynergyIndicator: React.FC<{
  synergies: string[];
  allGoals: Goal[];
  onGoalClick?: (goalId: string) => void;
}> = ({ synergies, allGoals, onGoalClick }) => {
  if (synergies.length === 0) return null;

  const relatedGoals = allGoals.filter((g) => synergies.includes(g.id));

  return (
    <div className="flex items-center gap-2 text-xs text-gray-400">
      <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
      <span>Connected to:</span>
      <div className="flex gap-1">
        {relatedGoals.map((goal) => (
          <button
            key={goal.id}
            onClick={() => onGoalClick?.(goal.id)}
            className="px-2 py-0.5 bg-gray-800 hover:bg-gray-700 rounded text-amber-400 transition-colors"
          >
            {goal.title}
          </button>
        ))}
      </div>
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================

export const GoalOrchestrationPanel: React.FC<GoalOrchestrationPanelProps> = ({
  goals,
  agents,
  synergies = [],
  timeline = [],
  transparencyMode = 'normal',
  onGoalSelect,
  onReprioritize,
  onPauseGoal,
  onResumeGoal,
  onRemoveGoal
}) => {
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'cards' | 'timeline' | 'graph'>('cards');
  const [filterStatus, setFilterStatus] = useState<GoalStatus | 'all'>('all');

  // Filter goals by status
  const filteredGoals = useMemo(() => {
    if (filterStatus === 'all') return goals;
    return goals.filter((g) => g.status === filterStatus);
  }, [goals, filterStatus]);

  // Group goals by category/synergy
  const goalGroups = useMemo(() => {
    const groups: { [key: string]: Goal[] } = {};

    filteredGoals.forEach((goal) => {
      // Group by category if exists, otherwise "Ungrouped"
      const key = goal.category || 'Other';
      if (!groups[key]) groups[key] = [];
      groups[key].push(goal);
    });

    return groups;
  }, [filteredGoals]);

  const selectedGoal = goals.find((g) => g.id === selectedGoalId);

  // ============================================================================
  // View: Cards (Default)
  // ============================================================================

  const renderCardsView = () => {
    return (
      <div className="space-y-6">
        {Object.entries(goalGroups).map(([groupName, groupGoals]) => (
          <div key={groupName}>
            <h3 className="text-lg font-semibold text-amber-400 mb-3">{groupName}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {groupGoals.map((goal) => (
                <GoalCard
                  key={goal.id}
                  goal={goal}
                  agents={agents}
                  allGoals={goals}
                  transparencyMode={transparencyMode}
                  onSelect={() => {
                    setSelectedGoalId(goal.id);
                    onGoalSelect?.(goal.id);
                  }}
                  onPause={() => onPauseGoal?.(goal.id)}
                  onResume={() => onResumeGoal?.(goal.id)}
                  onRemove={() => onRemoveGoal?.(goal.id)}
                  isExpanded={selectedGoalId === goal.id}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  // ============================================================================
  // View: Timeline
  // ============================================================================

  const renderTimelineView = () => {
    const sortedTimeline = [...timeline].sort((a, b) =>
      b.timestamp.getTime() - a.timestamp.getTime()
    );

    return (
      <div className="space-y-4">
        {sortedTimeline.map((event) => {
          const eventGoal = goals.find((g) => g.id === event.goalId);

          const eventColors = {
            milestone: 'bg-green-500',
            task_complete: 'bg-blue-500',
            blocker: 'bg-red-500',
            decision: 'bg-purple-500',
            agent_handoff: 'bg-amber-500'
          };

          return (
            <div key={event.id} className="flex gap-4">
              {/* Timeline line */}
              <div className="flex flex-col items-center">
                <div className={`w-3 h-3 rounded-full ${eventColors[event.type]}`} />
                <div className="w-0.5 flex-1 bg-gray-700 mt-2" />
              </div>

              {/* Event content */}
              <div className="flex-1 bg-gray-800/50 rounded-lg p-4 border border-gray-700">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <span className="text-xs text-gray-500">
                      {event.timestamp.toLocaleDateString()} {event.timestamp.toLocaleTimeString()}
                    </span>
                    <span className="mx-2 text-gray-600">•</span>
                    <span className="text-xs text-amber-400 uppercase">
                      {event.type.replace('_', ' ')}
                    </span>
                  </div>
                  {eventGoal && (
                    <span className="text-sm text-gray-400">{eventGoal.title}</span>
                  )}
                </div>
                <p className="text-gray-300">{event.description}</p>
                {event.agent && (
                  <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                    <span>by</span>
                    <span className="text-amber-400">{event.agent.name}</span>
                  </div>
                )}
                {event.impact && (
                  <div className="mt-2 text-xs text-gray-500 italic">{event.impact}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // ============================================================================
  // View: Graph (Simplified)
  // ============================================================================

  const renderGraphView = () => {
    return (
      <div className="bg-gray-800/50 rounded-lg p-6 border border-gray-700">
        <p className="text-gray-400 text-center">
          Interactive goal graph visualization
          <br />
          <span className="text-sm text-gray-500">
            (Shows goals as nodes, synergies as edges, click to drill down)
          </span>
        </p>

        {/* Simplified node list for now */}
        <div className="mt-4 space-y-2">
          {goals.map((goal) => (
            <div
              key={goal.id}
              className="flex items-center gap-3 p-3 bg-gray-900/50 rounded hover:bg-gray-900 transition-colors cursor-pointer"
              onClick={() => {
                setSelectedGoalId(goal.id);
                onGoalSelect?.(goal.id);
              }}
            >
              <div className={`w-3 h-3 rounded-full ${
                goal.status === 'active' ? 'bg-blue-500' :
                goal.status === 'completed' ? 'bg-green-500' :
                goal.status === 'blocked' ? 'bg-red-500' :
                'bg-yellow-500'
              }`} />
              <span className="flex-1 text-gray-300">{goal.title}</span>
              <span className="text-sm text-gray-500">{goal.progress}%</span>
              {goal.synergyWith && goal.synergyWith.length > 0 && (
                <span className="text-xs text-amber-400">{goal.synergyWith.length} links</span>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // ============================================================================
  // Controls & Filters
  // ============================================================================

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Mission Control</h2>
          <p className="text-gray-400">
            {filteredGoals.length} active goal{filteredGoals.length !== 1 ? 's' : ''}
            {transparencyMode !== 'simple' && ` across ${agents.length} agents`}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Transparency mode toggle */}
          <select
            value={transparencyMode}
            onChange={(e) => setViewMode(e.target.value as any)}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-300"
          >
            <option value="simple">Simple</option>
            <option value="normal">Normal</option>
            <option value="detailed">Detailed</option>
          </select>

          {/* View mode toggle */}
          <div className="flex bg-gray-800 rounded-lg border border-gray-700">
            <button
              onClick={() => setViewMode('cards')}
              className={`px-3 py-2 text-sm rounded-l-lg transition-colors ${
                viewMode === 'cards'
                  ? 'bg-amber-600 text-white'
                  : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              Cards
            </button>
            <button
              onClick={() => setViewMode('timeline')}
              className={`px-3 py-2 text-sm transition-colors ${
                viewMode === 'timeline'
                  ? 'bg-amber-600 text-white'
                  : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              Timeline
            </button>
            <button
              onClick={() => setViewMode('graph')}
              className={`px-3 py-2 text-sm rounded-r-lg transition-colors ${
                viewMode === 'graph'
                  ? 'bg-amber-600 text-white'
                  : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              Graph
            </button>
          </div>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-500">Filter:</span>
        {(['all', 'active', 'paused', 'completed', 'blocked'] as const).map((status) => (
          <button
            key={status}
            onClick={() => setFilterStatus(status)}
            className={`px-3 py-1 rounded text-sm transition-colors ${
              filterStatus === status
                ? 'bg-amber-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-gray-300'
            }`}
          >
            {status === 'all' ? 'All' : status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      {/* Main content */}
      {viewMode === 'cards' && renderCardsView()}
      {viewMode === 'timeline' && renderTimelineView()}
      {viewMode === 'graph' && renderGraphView()}

      {/* Selected goal detail panel */}
      {selectedGoal && (
        <GoalDetailPanel
          goal={selectedGoal}
          agents={agents}
          allGoals={goals}
          transparencyMode={transparencyMode}
          onClose={() => setSelectedGoalId(null)}
        />
      )}
    </div>
  );
};

// ============================================================================
// Sub-Components
// ============================================================================

interface GoalCardProps {
  goal: Goal;
  agents: AgentRef[];
  allGoals: Goal[];
  transparencyMode: TransparencyMode;
  onSelect: () => void;
  onPause: () => void;
  onResume: () => void;
  onRemove: () => void;
  isExpanded: boolean;
}

const GoalCard: React.FC<GoalCardProps> = ({
  goal,
  agents,
  allGoals,
  transparencyMode,
  onSelect,
  onPause,
  onResume,
  onRemove,
  isExpanded
}) => {
  const assignedAgents = agents.filter((a) => goal.assignedAgents.some((aa) => aa.id === a.id));

  return (
    <div
      className={`
        bg-gray-800/50 backdrop-blur rounded-lg border transition-all cursor-pointer
        ${isExpanded ? 'border-amber-500/50 shadow-lg shadow-amber-500/10' : 'border-gray-700 hover:border-gray-600'}
      `}
      onClick={onSelect}
    >
      <div className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <h3 className="font-semibold text-white">{goal.title}</h3>
          <StatusBadge status={goal.status} />
        </div>

        {/* Progress */}
        <div>
          <ProgressBar progress={goal.progress} status={goal.status} />
        </div>

        {/* Agent avatars (always shown in normal/detailed mode) */}
        {transparencyMode !== 'simple' && assignedAgents.length > 0 && (
          <div className="flex items-center justify-between">
            <AgentAvatars agents={assignedAgents} compact />
            {goal.deadline && (
              <span className="text-xs text-gray-500">
                Due {goal.deadline.toLocaleDateString()}
              </span>
            )}
          </div>
        )}

        {/* Synergy indicator (normal/detailed mode) */}
        {transparencyMode !== 'simple' && goal.synergyWith && (
          <SynergyIndicator
            synergies={goal.synergyWith}
            allGoals={allGoals}
          />
        )}

        {/* Detailed mode: Task count */}
        {transparencyMode === 'detailed' && (
          <div className="text-xs text-gray-500">
            {goal.tasks.filter((t) => t.status === 'completed').length} / {goal.tasks.length} tasks complete
          </div>
        )}
      </div>

      {/* Actions (on hover) */}
      <div className="px-4 pb-4 flex gap-2">
        {goal.status === 'active' && (
          <button
            onClick={(e) => { e.stopPropagation(); onPause(); }}
            className="flex-1 px-3 py-1.5 bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-400 rounded text-sm transition-colors"
          >
            Pause
          </button>
        )}
        {goal.status === 'paused' && (
          <button
            onClick={(e) => { e.stopPropagation(); onResume(); }}
            className="flex-1 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded text-sm transition-colors"
          >
            Resume
          </button>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded text-sm transition-colors"
        >
          Remove
        </button>
      </div>
    </div>
  );
};

interface GoalDetailPanelProps {
  goal: Goal;
  agents: AgentRef[];
  allGoals: Goal[];
  transparencyMode: TransparencyMode;
  onClose: () => void;
}

const GoalDetailPanel: React.FC<GoalDetailPanelProps> = ({
  goal,
  agents,
  allGoals,
  transparencyMode,
  onClose
}) => {
  const assignedAgents = agents.filter((a) => goal.assignedAgents.some((aa) => aa.id === a.id));

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-6">
      <div className="bg-gray-900 rounded-xl border border-gray-700 max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">{goal.title}</h2>
            <p className="text-gray-400 mt-1">{goal.description}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-800 rounded text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Progress overview */}
          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-400">Progress</span>
              <StatusBadge status={goal.status} />
            </div>
            <ProgressBar progress={goal.progress} status={goal.status} size="lg" />
            {goal.deadline && (
              <div className="mt-3 text-sm text-gray-500">
                Target: {goal.deadline.toLocaleDateString()}
              </div>
            )}
          </div>

          {/* Assigned agents */}
          <div>
            <h3 className="text-lg font-semibold text-white mb-3">Team</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {assignedAgents.map((agent) => (
                <div
                  key={agent.id}
                  className="bg-gray-800/50 rounded-lg p-4 border border-gray-700"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-600 to-amber-800 flex items-center justify-center text-white font-semibold">
                      {agent.name.charAt(0)}
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-white">{agent.name}</div>
                      <div className="text-xs text-gray-500">{agent.specialization.join(', ')}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-gray-400">{agent.currentTasks} tasks</div>
                      <div className="text-xs text-gray-500">{agent.capacity}% capacity</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Tasks */}
          <div>
            <h3 className="text-lg font-semibold text-white mb-3">Tasks</h3>
            <div className="space-y-2">
              {goal.tasks.map((task) => {
                const taskAgent = agents.find((a) => a.id === task.assignedAgent);
                return (
                  <div
                    key={task.id}
                    className="bg-gray-800/50 rounded-lg p-3 border border-gray-700 flex items-center gap-3"
                  >
                    <div className={`w-2 h-2 rounded-full ${
                      task.status === 'completed' ? 'bg-green-500' :
                      task.status === 'in-progress' ? 'bg-blue-500' :
                      task.status === 'blocked' ? 'bg-red-500' :
                      'bg-gray-500'
                    }`} />
                    <span className="flex-1 text-gray-300">{task.title}</span>
                    {taskAgent && (
                      <span className="text-xs text-amber-400">{taskAgent.name}</span>
                    )}
                    <div className="w-20">
                      <ProgressBar progress={task.progress} status={goal.status} size="sm" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Synergies */}
          {goal.synergyWith && goal.synergyWith.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-3">Connected Goals</h3>
              <SynergyIndicator
                synergies={goal.synergyWith}
                allGoals={allGoals}
              />
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-4 border-t border-gray-700">
            <button
              className="flex-1 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg font-semibold transition-colors"
            >
              View Full Strategy
            </button>
            <button
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors"
            >
              Reprioritize
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GoalOrchestrationPanel;
