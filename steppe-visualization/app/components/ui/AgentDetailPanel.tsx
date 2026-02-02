'use client';

import { X, Clock, CheckCircle, FileText, MapPin, Crown, ListOrdered, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Agent, Activity } from '@/app/types/agents';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface AgentDetailPanelProps {
  agent: Agent | null;
  activities: Activity[];
  isOpen: boolean;
  onClose: () => void;
}

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

export function AgentDetailPanel({ agent, activities, isOpen, onClose }: AgentDetailPanelProps) {
  if (!agent) return null;

  const status = STATUS_CONFIG[agent.status];

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: '100%', opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: '100%', opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="fixed top-0 right-0 z-50 h-full w-96 bg-black/90 backdrop-blur-xl border-l border-white/10 shadow-2xl"
        >
          <ScrollArea className="h-full">
            <div className="p-6 space-y-6">
              {/* Header */}
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="w-12 h-12 rounded-full flex items-center justify-center shadow-lg"
                    style={{
                      background: `linear-gradient(135deg, ${agent.theme.primary}, ${agent.theme.secondary})`,
                    }}
                  >
                    <Crown className="w-6 h-6 text-white" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-white">{agent.displayName}</h2>
                    <p className="text-sm text-white/60 capitalize">{agent.role} Agent</p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onClose}
                  className="text-white/50 hover:text-white hover:bg-white/10"
                >
                  <X className="w-5 h-5" />
                </Button>
              </div>

              {/* Status */}
              <div className="flex items-center gap-3">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-white border-none',
                    status.color.replace('bg-', 'bg-').replace('500', '500/20')
                  )}
                >
                  <span className={cn('w-2 h-2 rounded-full mr-2', status.color)} />
                  {status.label}
                </Badge>
                {agent.currentTask && (
                  <span className="text-sm text-white/60">
                    {Math.round(agent.currentTask.progress)}% complete
                  </span>
                )}
              </div>

              {/* Historical Context */}
              <Card className="bg-white/5 border-white/10 p-4">
                <div className="flex items-center gap-2 text-amber-400 mb-2">
                  <MapPin className="w-4 h-4" />
                  <span className="text-sm font-medium">{agent.historicalCapital}</span>
                </div>
                <p className="text-sm text-white/70 leading-relaxed">
                  {agent.historicalContext}
                </p>
                <div className="mt-3 text-xs text-white/40">
                  {agent.coordinates.lat.toFixed(1)}°N, {agent.coordinates.lng.toFixed(1)}°E
                </div>
              </Card>

              {/* Current Task */}
              {agent.currentTask && (
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <Clock className="w-4 h-4" />
                    Current Task
                  </h3>
                  <Card className="bg-white/5 border-white/10 p-4 space-y-3">
                    <div>
                      <h4 className="text-white font-medium">{agent.currentTask.title}</h4>
                      <p className="text-sm text-white/60 mt-1">
                        {agent.currentTask.description}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs text-white/50">
                        <span>Progress</span>
                        <span>{Math.round(agent.currentTask.progress)}%</span>
                      </div>
                      <Progress value={agent.currentTask.progress} className="h-2" />
                    </div>
                    <div className="flex justify-between text-xs text-white/40">
                      <span>Started {new Date(agent.currentTask.startedAt).toLocaleTimeString()}</span>
                      {agent.currentTask.estimatedCompletion && (
                        <span>Est. {new Date(agent.currentTask.estimatedCompletion).toLocaleTimeString()}</span>
                      )}
                    </div>
                  </Card>
                </div>
              )}

              {/* Task Queue */}
              {agent.queue.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <ListOrdered className="w-4 h-4" />
                    Task Queue ({agent.queue.length})
                  </h3>
                  <div className="space-y-2">
                    {agent.queue.map((task, index) => (
                      <Card
                        key={task.id}
                        className="bg-white/5 border-white/10 p-3 hover:bg-white/10 transition-colors"
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-6 h-6 rounded-full bg-white/10 flex items-center justify-center text-xs text-white/60">
                            {index + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <h4 className="text-sm font-medium text-white truncate">
                                {task.title}
                              </h4>
                              {task.priority === 'high' && (
                                <AlertCircle className="w-3 h-3 text-red-400" />
                              )}
                            </div>
                            <div className="flex items-center gap-3 mt-1">
                              <Badge
                                variant="outline"
                                className={`
                                  text-xs border-none
                                  ${task.priority === 'high' ? 'bg-red-500/20 text-red-300' : ''}
                                  ${task.priority === 'medium' ? 'bg-amber-500/20 text-amber-300' : ''}
                                  ${task.priority === 'low' ? 'bg-green-500/20 text-green-300' : ''}
                                `}
                              >
                                {task.priority}
                              </Badge>
                              <span className="text-xs text-white/40">
                                ~{task.estimatedDuration} min
                              </span>
                            </div>
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              {/* Metrics */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-white/80">Today&apos;s Metrics</h3>
                <div className="grid grid-cols-2 gap-3">
                  <Card className="bg-white/5 border-white/10 p-3">
                    <div className="text-2xl font-bold text-white">{agent.metrics.tasksCompleted}</div>
                    <div className="text-xs text-white/50">Tasks Completed</div>
                  </Card>
                  <Card className="bg-white/5 border-white/10 p-3">
                    <div className="text-2xl font-bold text-white">{agent.metrics.itemsProduced}</div>
                    <div className="text-xs text-white/50">Items Produced</div>
                  </Card>
                  <Card className="bg-white/5 border-white/10 p-3">
                    <div className="text-2xl font-bold text-white">
                      {Math.floor(agent.metrics.activeTimeMinutes / 60)}h {agent.metrics.activeTimeMinutes % 60}m
                    </div>
                    <div className="text-xs text-white/50">Active Time</div>
                  </Card>
                  <Card className="bg-white/5 border-white/10 p-3">
                    <div className="text-2xl font-bold text-white">
                      {new Date(agent.metrics.lastActiveAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                    <div className="text-xs text-white/50">Last Active</div>
                  </Card>
                </div>
              </div>

              {/* Recent Activity */}
              {activities.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <FileText className="w-4 h-4" />
                    Recent Activity
                  </h3>
                  <div className="space-y-2">
                    {activities.slice(0, 5).map((activity) => (
                      <Card
                        key={activity.id}
                        className="bg-white/5 border-white/10 p-3 hover:bg-white/10 transition-colors"
                      >
                        <div className="flex items-start gap-3">
                          <span className="text-lg">{ACTIVITY_ICONS[activity.type]}</span>
                          <div className="flex-1 min-w-0">
                            <h4 className="text-sm font-medium text-white truncate">
                              {activity.title}
                            </h4>
                            <p className="text-xs text-white/50 mt-0.5">
                              {activity.description}
                            </p>
                            <div className="text-xs text-white/30 mt-1">
                              {new Date(activity.timestamp).toLocaleTimeString()}
                            </div>
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              {/* Camp Info */}
              <Card className="bg-white/5 border-white/10 p-4">
                <h3 className="text-sm font-semibold text-white/80 mb-2 capitalize">
                  {agent.camp.type.replace('-', ' ')}
                </h3>
                <p className="text-sm text-white/60">{agent.camp.description}</p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {agent.camp.props.map((prop) => (
                    <Badge key={prop} variant="outline" className="text-white/50 border-white/20 text-xs">
                      {prop}
                    </Badge>
                  ))}
                </div>
              </Card>
            </div>
          </ScrollArea>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
