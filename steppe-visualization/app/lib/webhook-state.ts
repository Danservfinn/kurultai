// Shared state for webhook data
// In a production environment, this should be replaced with Redis or a database

interface AgentActivity {
  type: string;
  title: string;
  description: string;
  timestamp: string;
}

interface AgentState {
  status: string;
  lastUpdate: Date;
  currentTask?: {
    id: string;
    title: string;
    description: string;
    progress: number;
  };
  activities: AgentActivity[];
}

export class WebhookStateStore {
  private state = new Map<string, AgentState>();

  private getOrCreate(agentId: string): AgentState {
    let existing = this.state.get(agentId);
    if (!existing) {
      existing = {
        status: 'idle',
        lastUpdate: new Date(),
        activities: [],
      };
      this.state.set(agentId, existing);
    }
    return existing;
  }

  updateStatus(agentId: string, status: string): void {
    const state = this.getOrCreate(agentId);
    state.status = status;
    state.lastUpdate = new Date();
  }

  updateTask(agentId: string, task: AgentState['currentTask']): void {
    const state = this.getOrCreate(agentId);
    state.currentTask = task;
    state.lastUpdate = new Date();
  }

  addActivity(agentId: string, activity: AgentActivity): void {
    const state = this.getOrCreate(agentId);
    state.activities.unshift(activity);
    // Keep only last 50
    if (state.activities.length > 50) {
      state.activities = state.activities.slice(0, 50);
    }
    state.lastUpdate = new Date();
  }

  heartbeat(agentId: string): void {
    const state = this.getOrCreate(agentId);
    state.lastUpdate = new Date();
  }

  getAll(): Array<{ id: string } & AgentState> {
    return Array.from(this.state.entries()).map(([id, state]) => ({
      id,
      ...state,
    }));
  }

  get(agentId: string): ({ id: string } & AgentState) | undefined {
    const state = this.state.get(agentId);
    return state ? { id: agentId, ...state } : undefined;
  }

  // Check if agent has been updated recently (within last 5 minutes)
  isAlive(agentId: string): boolean {
    const state = this.state.get(agentId);
    if (!state) return false;
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);
    return state.lastUpdate > fiveMinutesAgo;
  }

  // Get agents that have been updated recently
  getAliveAgents(): string[] {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);
    return Array.from(this.state.entries())
      .filter(([, state]) => state.lastUpdate > fiveMinutesAgo)
      .map(([id]) => id);
  }
}

// Global singleton instance
export const webhookStore = new WebhookStateStore();
