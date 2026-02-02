'use client';

import { useEffect, useRef } from 'react';
import { useAgentStore } from '@/app/stores/agentStore';
import { Activity, Deliverable } from '@/app/types/agents';

// Map file patterns to agents and activity types
const FILE_PATTERNS = [
  { pattern: /kublai/i, agentId: 'kublai', type: 'automation' as const },
  { pattern: /mongke/i, agentId: 'mongke', type: 'research' as const },
  { pattern: /ogedei/i, agentId: 'ogedei', type: 'content' as const },
  { pattern: /temujin/i, agentId: 'temujin', type: 'security' as const },
  { pattern: /jochi/i, agentId: 'jochi', type: 'analysis' as const },
  { pattern: /chagatai/i, agentId: 'chagatai', type: 'operations' as const },
];

const DELIVERABLES_PATH = '/data/workspace/deliverables';

export function useFileWatcher() {
  const { updateAgentStatus, addActivity, addDeliverable, updateAgentTask } = useAgentStore();
  const watchedFiles = useRef<Set<string>>(new Set());

  useEffect(() => {
    // For client-side, we'll use polling since chokidar requires Node.js
    const pollInterval = setInterval(async () => {
      try {
        // Fetch deliverables from API
        const response = await fetch('/api/deliverables');
        if (!response.ok) return;

        const data = await response.json();
        const files: string[] = data.files || [];

        // Check for new files
        for (const file of files) {
          if (!watchedFiles.current.has(file)) {
            watchedFiles.current.add(file);
            handleNewFile(file);
          }
        }
      } catch (error) {
        // Silent fail - will retry on next poll
      }
    }, 5000); // Poll every 5 seconds

    return () => clearInterval(pollInterval);
  }, []);

  function handleNewFile(filePath: string) {
    const fileName = filePath.split('/').pop() || '';

    // Find matching agent
    const match = FILE_PATTERNS.find((p) => p.pattern.test(fileName));
    if (!match) return;

    const { agentId, type } = match;

    // Update agent status
    updateAgentStatus(agentId, 'working');

    // Create activity
    const activity: Activity = {
      id: `activity-${Date.now()}`,
      agentId,
      type,
      title: `Created ${fileName}`,
      description: `New deliverable created at ${filePath}`,
      timestamp: new Date(),
      deliverablePath: filePath,
    };
    addActivity(activity);

    // Create deliverable
    const deliverable: Deliverable = {
      id: `deliverable-${Date.now()}`,
      agentId,
      type,
      title: fileName,
      path: filePath,
      createdAt: new Date(),
      modifiedAt: new Date(),
      size: 0,
    };
    addDeliverable(deliverable);

    // Simulate task progress
    simulateTaskProgress(agentId, fileName);

    // Reset status after delay
    setTimeout(() => {
      updateAgentStatus(agentId, 'idle');
    }, 30000);
  }

  function simulateTaskProgress(agentId: string, taskName: string) {
    const task = {
      id: `task-${Date.now()}`,
      title: `Processing ${taskName}`,
      description: 'Analyzing and integrating deliverable',
      progress: 0,
      startedAt: new Date(),
      estimatedCompletion: new Date(Date.now() + 5 * 60 * 1000), // 5 min estimate
    };

    updateAgentTask(agentId, task);

    // Simulate progress updates
    let progress = 0;
    const interval = setInterval(() => {
      progress += 10;
      if (progress >= 100) {
        clearInterval(interval);
        updateAgentTask(agentId, {
          ...task,
          progress: 100,
        });
        setTimeout(() => updateAgentTask(agentId, undefined), 2000);
      } else {
        updateAgentTask(agentId, { ...task, progress });
      }
    }, 3000);
  }
}
