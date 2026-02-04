'use client';

import { useEffect, useState, useCallback } from 'react';
import { AgentStatusCard } from './components/AgentStatusCard';
import { TaskBoard } from './components/TaskBoard';
import { NotificationCenter } from './components/NotificationCenter';
import { CollaborationGraph } from './components/CollaborationGraph';
import { MemoryStats } from './components/MemoryStats';
import { SystemHealth } from './components/SystemHealth';
import { ActivityLog } from './components/ActivityLog';

// Agent definitions from neo4j.md
const AGENTS = [
  {
    id: 'main',
    name: 'Kublai',
    role: 'Squad Lead / Router',
    color: '#FFD700',
    capabilities: ['orchestration', 'delegation', 'synthesis'],
    personality: 'Strategic leader with broad oversight',
  },
  {
    id: 'researcher',
    name: 'Möngke',
    role: 'Researcher',
    color: '#4A90D9',
    capabilities: ['deep_research', 'fact_checking', 'synthesis'],
    personality: 'Thorough and methodical investigator',
  },
  {
    id: 'writer',
    name: 'Chagatai',
    role: 'Content Writer',
    color: '#9B59B6',
    capabilities: ['content_creation', 'editing', 'storytelling'],
    personality: 'Articulate and creative communicator',
  },
  {
    id: 'developer',
    name: 'Temüjin',
    role: 'Developer/Security Lead',
    color: '#27AE60',
    capabilities: ['coding', 'security_audit', 'architecture', 'vulnerability_assessment'],
    personality: 'Pragmatic builder with security focus',
  },
  {
    id: 'analyst',
    name: 'Jochi',
    role: 'Analyst/Performance Lead',
    color: '#E74C3C',
    capabilities: ['data_analysis', 'metrics', 'performance_monitoring', 'backend_code_review'],
    personality: 'Detail-oriented pattern finder',
  },
  {
    id: 'ops',
    name: 'Ögedei',
    role: 'Operations',
    color: '#F39C12',
    capabilities: ['process_management', 'task_coordination', 'monitoring'],
    personality: 'Efficient organizer and process optimizer',
  },
];

// Task type from neo4j schema
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

// Notification type from neo4j schema
interface Notification {
  id: string;
  type: 'task_complete' | 'task_blocked' | 'insight';
  task_id: string;
  from_agent: string;
  summary: string;
  created_at: string;
  read: boolean;
}

// Activity type
interface Activity {
  id: string;
  agent_id: string;
  type: string;
  title: string;
  description: string;
  timestamp: string;
}

// Memory stats type
interface MemoryStats {
  research_count: number;
  content_count: number;
  analysis_count: number;
  application_count: number;
  insight_count: number;
  concept_count: number;
  task_count: number;
  notification_count: number;
}

// Collaboration relationship
interface Collaboration {
  from: string;
  to: string;
  type: 'LEARNED' | 'COLLABORATES_WITH' | 'CREATED';
  timestamp: string;
}

export default function ControlPanelPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [agents, setAgents] = useState(AGENTS);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const [collaborations, setCollaborations] = useState<Collaboration[]>([]);
  const [systemHealth, setSystemHealth] = useState({
    neo4j: 'unknown',
    openclaw: 'unknown',
    signal: 'unknown',
  });
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [isLoading, setIsLoading] = useState(true);

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      // Fetch agent statuses
      const agentsRes = await fetch('/api/agents');
      if (agentsRes.ok) {
        const agentData = await agentsRes.json();
        // Merge with static agent definitions
        setAgents(prev =>
          prev.map(agent => {
            const liveData = agentData.agents?.find((a: any) => a.id === agent.id);
            return liveData
              ? { ...agent, status: liveData.status, lastActive: liveData.lastActive }
              : agent;
          })
        );
      }

      // Fetch tasks
      const tasksRes = await fetch('/api/tasks');
      if (tasksRes.ok) {
        const taskData = await tasksRes.json();
        setTasks(taskData.tasks || []);
      }

      // Fetch webhook state for activities
      const webhookRes = await fetch('/api/webhook');
      if (webhookRes.ok) {
        const webhookData = await webhookRes.json();
        // Transform webhook data into activities
        const allActivities: Activity[] = [];
        webhookData.agents?.forEach((agent: any) => {
          agent.activities?.forEach((activity: any) => {
            allActivities.push({
              id: `${agent.id}-${activity.timestamp}`,
              agent_id: agent.id,
              type: activity.type,
              title: activity.title,
              description: activity.description,
              timestamp: activity.timestamp,
            });
          });
        });
        setActivities(allActivities.sort((a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        ));
      }

      // Fetch memory stats (from Neo4j)
      const statsRes = await fetch('/api/memory-stats');
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setMemoryStats(statsData);
      }

      // Fetch collaboration data
      const collabRes = await fetch('/api/collaborations');
      if (collabRes.ok) {
        const collabData = await collabRes.json();
        setCollaborations(collabData.collaborations || []);
      }

      // Fetch notifications
      const notifRes = await fetch('/api/notifications');
      if (notifRes.ok) {
        const notifData = await notifRes.json();
        setNotifications(notifData.notifications || []);
      }

      // Fetch system health
      const healthRes = await fetch('/api/health');
      if (healthRes.ok) {
        const healthData = await healthRes.json();
        setSystemHealth(healthData.services || systemHealth);
      }

      setLastUpdate(new Date());
    } catch (error) {
      console.error('Error fetching control panel data:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch and polling
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [fetchData]);

  // Filter tasks by status
  const pendingTasks = tasks.filter(t => t.status === 'pending');
  const inProgressTasks = tasks.filter(t => t.status === 'in_progress');
  const completedTasks = tasks.filter(t => t.status === 'completed');
  const blockedTasks = tasks.filter(t => t.status === 'blocked' || t.status === 'escalated');

  // Filter notifications
  const unreadNotifications = notifications.filter(n => !n.read);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-[1920px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-amber-700 flex items-center justify-center shadow-lg shadow-amber-500/20">
                <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
                  Mission Control
                </h1>
                <p className="text-sm text-slate-400">Neo4j Multi-Agent Architecture Monitor</p>
              </div>
            </div>

            <div className="flex items-center gap-6">
              <SystemHealth health={systemHealth} />
              <div className="text-right">
                <p className="text-xs text-slate-500 uppercase tracking-wider">Last Update</p>
                <p className="text-sm text-slate-300 font-mono">
                  {lastUpdate.toLocaleTimeString()}
                </p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-[1920px] mx-auto px-6 py-6">
        {isLoading ? (
          <div className="flex items-center justify-center h-96">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 border-4 border-amber-500/30 border-t-amber-500 rounded-full animate-spin" />
              <p className="text-slate-400">Loading mission control data...</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-12 gap-6">
            {/* Agent Status Grid */}
            <div className="col-span-12">
              <h2 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                Agent Status
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                {agents.map(agent => (
                  <AgentStatusCard
                    key={agent.id}
                    agent={agent}
                    isSelected={selectedAgent === agent.id}
                    onClick={() => setSelectedAgent(selectedAgent === agent.id ? null : agent.id)}
                    taskCount={tasks.filter(t => t.assigned_to === agent.id).length}
                  />
                ))}
              </div>
            </div>

            {/* Task Board */}
            <div className="col-span-12 lg:col-span-8">
              <TaskBoard
                pending={pendingTasks}
                inProgress={inProgressTasks}
                completed={completedTasks}
                blocked={blockedTasks}
                selectedAgent={selectedAgent}
              />
            </div>

            {/* Notification Center */}
            <div className="col-span-12 lg:col-span-4">
              <NotificationCenter
                notifications={notifications}
                unreadCount={unreadNotifications.length}
              />
            </div>

            {/* Collaboration Graph */}
            <div className="col-span-12 lg:col-span-6">
              <CollaborationGraph
                agents={agents}
                collaborations={collaborations}
                selectedAgent={selectedAgent}
              />
            </div>

            {/* Memory Stats */}
            <div className="col-span-12 lg:col-span-3">
              <MemoryStats stats={memoryStats} />
            </div>

            {/* Activity Log */}
            <div className="col-span-12 lg:col-span-3">
              <ActivityLog
                activities={activities}
                selectedAgent={selectedAgent}
                agents={agents}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
