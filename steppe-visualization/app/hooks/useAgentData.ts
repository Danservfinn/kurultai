'use client';

import { useEffect, useState } from 'react';
import { useAgentStore } from '@/app/stores/agentStore';

interface LiveAgentData {
  id: string;
  name: string;
  role: string;
  status: string;
  lastActive: string | null;
  messageCount: number;
}

interface TasksResponse {
  tasks: Array<{
    path: string;
    status: string;
    metadata?: {
      title?: string;
      assignedTo?: string;
      priority?: string;
      created?: string;
    };
  }>;
  tasksByAgent: Record<string, any[]>;
  summary: {
    total: number;
    byStatus: Record<string, number>;
  };
}

interface AgentsResponse {
  source: string;
  agents: LiveAgentData[];
  gatewayError?: string;
}

// Map gateway agent IDs to visualization agent IDs
function mapGatewayToViz(gatewayId: string): string {
  const mapping: Record<string, string> = {
    'main': 'kublai',
    'researcher': 'mongke',
    'writer': 'ogedei',
    'developer': 'temujin',
    'analyst': 'jochi',
    'ops': 'chagatai',
  };
  return mapping[gatewayId] || gatewayId;
}

export function useAgentData() {
  const { setAgents, updateAgentStatus, addActivity } = useAgentStore();
  const [isConnected, setIsConnected] = useState(false);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  useEffect(() => {
    let mounted = true;

    async function fetchAgentStatus() {
      try {
        // Fetch agent status from gateway
        const response = await fetch('/api/agents');
        if (!response.ok) return;

        const data: AgentsResponse = await response.json();

        if (data.source === 'gateway' && mounted) {
          setIsConnected(true);

          // Update agent statuses based on gateway data
          for (const agent of data.agents) {
            const vizId = mapGatewayToViz(agent.id);
            updateAgentStatus(vizId, agent.status === 'working' ? 'working' : 'idle');
          }
        } else {
          setIsConnected(false);
        }

        setLastFetch(new Date());
      } catch (error) {
        console.error('Failed to fetch agent status:', error);
        setIsConnected(false);
      }
    }

    async function fetchTasks() {
      try {
        const response = await fetch('/api/tasks');
        if (!response.ok) return;

        const data: TasksResponse = await response.json();

        if (data.tasksByAgent && mounted) {
          // Create activities for new tasks
          for (const [agentId, tasks] of Object.entries(data.tasksByAgent)) {
            for (const task of tasks as any[]) {
              // Check if task metadata exists
              if (task.metadata?.title) {
                addActivity({
                  id: `task-${task.path}`,
                  agentId: mapGatewayToViz(agentId),
                  type: 'operations',
                  title: task.metadata.title,
                  description: `Task in ${task.status}`,
                  timestamp: new Date(task.metadata.created || Date.now()),
                });
              }
            }
          }
        }
      } catch (error) {
        console.error('Failed to fetch tasks:', error);
      }
    }

    // Initial fetch
    fetchAgentStatus();
    fetchTasks();

    // Poll every 10 seconds
    const interval = setInterval(() => {
      fetchAgentStatus();
      fetchTasks();
    }, 10000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [updateAgentStatus, addActivity]);

  return { isConnected, lastFetch };
}
