'use client';

import { useState, useEffect } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { Agent, Activity } from '../types/agents';
import { ArrowLeft, Clock, ListOrdered, Activity as ActivityIcon, CheckCircle, AlertCircle, Crown } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const STATUS_CONFIG: Record<Agent['status'], { label: string; color: string }> = {
  idle: { label: 'Idle', color: 'bg-green-500' },
  working: { label: 'Working', color: 'bg-blue-500' },
  reviewing: { label: 'Reviewing', color: 'bg-amber-500' },
  alert: { label: 'Alert', color: 'bg-red-500' },
  offline: { label: 'Offline', color: 'bg-gray-500' },
};

const ACTIVITY_ICONS: Record<Activity['type'], string> = {
  research: '🔍',
  content: '📝',
  security: '🔒',
  'code-review': '👁️',
  automation: '⚙️',
  analysis: '📊',
  operations: '📦',
};

interface AgentCardProps {
  agent: Agent;
  activities: Activity[];
}

function AgentCard({ agent, activities }: AgentCardProps) {
  const status = STATUS_CONFIG[agent.status];

  return (
    <Card className="bg-black/40 border-white/10 backdrop-blur-sm overflow-hidden flex flex-col h-full">
      {/* Header */}
      <div
        className="p-4 border-b border-white/10"
        style={{
          background: `linear-gradient(135deg, ${agent.theme.primary}20, ${agent.theme.secondary}10)`,
        }}
      >
        <div className="flex items-start gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center shadow-lg flex-shrink-0"
            style={{
              background: `linear-gradient(135deg, ${agent.theme.primary}, ${agent.theme.secondary})`,
            }}
          >
            <Crown className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-white truncate">{agent.displayName}</h3>
              <Badge
                variant="outline"
                className={cn('text-white border-none shrink-0', status.color.replace('bg-', 'bg-').replace('500', '500/20'))}
              >
                <span className={cn('w-1.5 h-1.5 rounded-full mr-1.5', status.color)} />
                {status.label}
              </Badge>
            </div>
            <p className="text-sm text-white/60 capitalize">{agent.role} Agent</p>
            <p className="text-xs text-white/40 mt-1">{agent.historicalCapital}</p>
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {/* Current Task */}
          {agent.currentTask && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-white/80">
                <Clock className="w-4 h-4" />
                <span>Current Task</span>
                <span className="ml-auto text-white/50">{Math.round(agent.currentTask.progress)}%</span>
              </div>
              <Card className="bg-white/5 border-white/10 p-3">
                <h4 className="text-white font-medium text-sm">{agent.currentTask.title}</h4>
                <p className="text-xs text-white/50 mt-1 line-clamp-2">{agent.currentTask.description}</p>
                <Progress value={agent.currentTask.progress} className="h-1.5 mt-2" />
              </Card>
            </div>
          )}

          {/* Queue */}
          {agent.queue.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-white/80">
                <ListOrdered className="w-4 h-4" />
                <span>Queue ({agent.queue.length})</span>
              </div>
              <div className="space-y-1.5">
                {agent.queue.slice(0, 5).map((task, index) => (
                  <Card
                    key={task.id}
                    className={cn(
                      'bg-white/5 border-white/10 p-2.5',
                      task.priority === 'high' && 'border-red-500/30'
                    )}
                  >
                    <div className="flex items-start gap-2">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-white/10 flex items-center justify-center text-xs text-white/50">
                        {index + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-white truncate">{task.title}</span>
                          {task.priority === 'high' && <AlertCircle className="w-3 h-3 text-red-400 shrink-0" />}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge
                            variant="outline"
                            className={cn(
                              'text-xs border-none',
                              task.priority === 'high' && 'bg-red-500/20 text-red-300',
                              task.priority === 'medium' && 'bg-amber-500/20 text-amber-300',
                              task.priority === 'low' && 'bg-green-500/20 text-green-300'
                            )}
                          >
                            {task.priority}
                          </Badge>
                          <span className="text-xs text-white/40">~{task.estimatedDuration} min</span>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
                {agent.queue.length > 5 && (
                  <p className="text-xs text-white/40 text-center py-1">
                    +{agent.queue.length - 5} more tasks
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Activity Log */}
          {activities.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-white/80">
                <ActivityIcon className="w-4 h-4" />
                <span>Activity Log</span>
                <span className="ml-auto text-xs text-white/40">Last 24h</span>
              </div>
              <div className="space-y-1.5">
                {activities.slice(0, 10).map((activity) => (
                  <Card key={activity.id} className="bg-white/5 border-white/10 p-2.5">
                    <div className="flex items-start gap-2">
                      <span className="text-sm shrink-0">{ACTIVITY_ICONS[activity.type]}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-white truncate">{activity.title}</p>
                        <p className="text-xs text-white/40 truncate">{activity.description}</p>
                        <p className="text-xs text-white/30 mt-0.5">
                          {new Date(activity.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </p>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Metrics Summary */}
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-white/10">
            <Card className="bg-white/5 border-white/10 p-2 text-center">
              <div className="text-lg font-bold text-white">{agent.metrics.tasksCompleted}</div>
              <div className="text-xs text-white/40">Completed</div>
            </Card>
            <Card className="bg-white/5 border-white/10 p-2 text-center">
              <div className="text-lg font-bold text-white">{agent.metrics.itemsProduced}</div>
              <div className="text-xs text-white/40">Produced</div>
            </Card>
          </div>
        </div>
      </ScrollArea>
    </Card>
  );
}

export default function MissionControlPage() {
  const { agents, getAgentActivities } = useAgentStore();
  const [agentActivities, setAgentActivities] = useState<Record<string, Activity[]>>({});

  // Load activities for all agents
  useEffect(() => {
    const activities: Record<string, Activity[]> = {};
    agents.forEach((agent) => {
      activities[agent.id] = getAgentActivities(agent.id);
    });
    setAgentActivities(activities);
  }, [agents, getAgentActivities]);

  return (
    <main className="min-h-screen bg-gradient-to-br from-black via-gray-950 to-black">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-black/80 backdrop-blur-xl border-b border-white/10">
        <div className="max-w-[1800px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => window.location.href = '/'}
                className="text-white/70 hover:text-white hover:bg-white/10"
              >
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div>
                <h1 className="text-2xl font-bold text-white tracking-tight">
                  Mission Control
                </h1>
                <p className="text-sm text-white/60">
                  Real-time Agent Operations • {agents.length} Active Agents
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-white/70 border-white/20">
                <span className="w-2 h-2 rounded-full bg-green-500 mr-2 animate-pulse" />
                Live
              </Badge>
            </div>
          </div>
        </div>
      </header>

      {/* Agent Grid */}
      <div className="max-w-[1800px] mx-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <div key={agent.id} className="h-[500px]">
              <AgentCard
                agent={agent}
                activities={agentActivities[agent.id] || []}
              />
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
