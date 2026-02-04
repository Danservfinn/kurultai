import { NextResponse } from 'next/server';

// Mock notifications - in production this would query Neo4j Notification nodes
export async function GET() {
  const notifications = [
    {
      id: 'notif-1',
      type: 'task_complete',
      task_id: 'task-123',
      from_agent: 'researcher',
      summary: 'Research on Neo4j vector indexes completed',
      created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
      read: false,
    },
    {
      id: 'notif-2',
      type: 'task_blocked',
      task_id: 'task-124',
      from_agent: 'developer',
      summary: 'Circuit breaker implementation blocked - needs retry logic',
      created_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
      read: false,
    },
    {
      id: 'notif-3',
      type: 'insight',
      task_id: 'task-125',
      from_agent: 'analyst',
      summary: 'Detected pattern: 80% of tasks delegated to Temüjin are security-related',
      created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
      read: true,
    },
    {
      id: 'notif-4',
      type: 'task_complete',
      task_id: 'task-126',
      from_agent: 'writer',
      summary: 'Documentation for multi-agent architecture completed',
      created_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
      read: true,
    },
    {
      id: 'notif-5',
      type: 'task_blocked',
      task_id: 'task-127',
      from_agent: 'analyst',
      summary: 'Performance analysis blocked - missing metrics from Jochi',
      created_at: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
      read: true,
    },
  ];

  return NextResponse.json({ notifications });
}
