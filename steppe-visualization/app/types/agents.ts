export type AgentRole =
  | 'coordinator'
  | 'researcher'
  | 'writer'
  | 'developer'
  | 'analyst'
  | 'operations';

export type AgentStatus =
  | 'idle'
  | 'working'
  | 'reviewing'
  | 'alert'
  | 'offline';

export interface Agent {
  id: string;
  name: string;
  role: AgentRole;
  displayName: string;
  description: string;
  historicalCapital: string;
  historicalContext: string;

  // Geographic position (latitude, longitude)
  coordinates: {
    lat: number;
    lng: number;
  };

  // 3D world position (normalized for visualization)
  position: {
    x: number;
    z: number;
    elevation: number;
  };

  // Visual theme
  theme: {
    primary: string;
    secondary: string;
    glow: string;
  };

  // Current state
  status: AgentStatus;
  currentTask?: {
    id: string;
    title: string;
    description: string;
    progress: number;
    startedAt: Date;
    estimatedCompletion?: Date;
  };

  // Task queue
  queue: {
    id: string;
    title: string;
    priority: 'low' | 'medium' | 'high';
    estimatedDuration: number; // minutes
  }[];

  // Statistics
  metrics: {
    tasksCompleted: number;
    itemsProduced: number;
    activeTimeMinutes: number;
    lastActiveAt: Date;
  };

  // Camp description
  camp: {
    type: string;
    description: string;
    props: string[];
  };
}

export interface Activity {
  id: string;
  agentId: string;
  type: 'research' | 'content' | 'security' | 'code-review' | 'automation' | 'analysis' | 'operations';
  title: string;
  description: string;
  timestamp: Date;
  deliverablePath?: string;
  metadata?: Record<string, any>;
}

export interface Deliverable {
  id: string;
  agentId: string;
  type: Activity['type'];
  title: string;
  path: string;
  createdAt: Date;
  modifiedAt: Date;
  size: number;
  excerpt?: string;
}
