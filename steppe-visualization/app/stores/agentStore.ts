'use client';

import { create } from 'zustand';
import { Agent, Activity, Deliverable } from '@/app/types/agents';
import { AGENTS } from '@/app/lib/agents';

interface AgentState {
  // Data
  agents: Agent[];
  activities: Activity[];
  deliverables: Deliverable[];

  // UI State
  selectedAgentId: string | null;
  isDetailPanelOpen: boolean;

  // Actions
  setAgents: (agents: Agent[]) => void;
  updateAgent: (agentId: string, updates: Partial<Agent>) => void;
  updateAgentStatus: (agentId: string, status: Agent['status']) => void;
  updateAgentTask: (agentId: string, task: Agent['currentTask']) => void;
  addActivity: (activity: Activity) => void;
  addDeliverable: (deliverable: Deliverable) => void;
  selectAgent: (agentId: string | null) => void;
  toggleDetailPanel: (open?: boolean) => void;

  // Derived
  getSelectedAgent: () => Agent | undefined;
  getAgentActivities: (agentId: string) => Activity[];
  getAgentDeliverables: (agentId: string) => Deliverable[];
}

export const useAgentStore = create<AgentState>((set, get) => ({
  // Initial data
  agents: AGENTS,
  activities: [],
  deliverables: [],
  selectedAgentId: null,
  isDetailPanelOpen: false,

  // Actions
  setAgents: (agents) => set({ agents }),

  updateAgent: (agentId, updates) =>
    set((state) => ({
      agents: state.agents.map((agent) =>
        agent.id === agentId ? { ...agent, ...updates } : agent
      ),
    })),

  updateAgentStatus: (agentId, status) =>
    set((state) => ({
      agents: state.agents.map((agent) =>
        agent.id === agentId
          ? { ...agent, status, metrics: { ...agent.metrics, lastActiveAt: new Date() } }
          : agent
      ),
    })),

  updateAgentTask: (agentId, task) =>
    set((state) => ({
      agents: state.agents.map((agent) =>
        agent.id === agentId ? { ...agent, currentTask: task } : agent
      ),
    })),

  addActivity: (activity) =>
    set((state) => ({
      activities: [activity, ...state.activities].slice(0, 100), // Keep last 100
    })),

  addDeliverable: (deliverable) =>
    set((state) => ({
      deliverables: [deliverable, ...state.deliverables],
    })),

  selectAgent: (agentId) =>
    set({
      selectedAgentId: agentId,
      isDetailPanelOpen: agentId !== null,
    }),

  toggleDetailPanel: (open) =>
    set((state) => ({
      isDetailPanelOpen: open ?? !state.isDetailPanelOpen,
    })),

  // Derived getters
  getSelectedAgent: () => {
    const { agents, selectedAgentId } = get();
    return agents.find((a) => a.id === selectedAgentId);
  },

  getAgentActivities: (agentId) => {
    return get().activities.filter((a) => a.agentId === agentId);
  },

  getAgentDeliverables: (agentId) => {
    return get().deliverables.filter((d) => d.agentId === agentId);
  },
}));
