import { NextResponse } from 'next/server';
import { webhookStore } from '../../lib/webhook-state';

interface WebhookPayload {
  source: 'kublai' | 'mongke' | 'ogedei' | 'temujin' | 'jochi' | 'chagatai' | 'main' | 'researcher' | 'writer' | 'developer' | 'analyst' | 'ops';
  agentId?: string;
  eventType: 'status' | 'task' | 'heartbeat' | 'activity';
  data: {
    status?: 'idle' | 'working' | 'reviewing' | 'alert' | 'offline';
    task?: {
      id: string;
      title: string;
      description: string;
      progress: number;
    };
    activity?: {
      type: string;
      title: string;
      description: string;
    };
    timestamp?: string;
  };
}

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    const payload: WebhookPayload = await request.json();

    // Map source to visualization agent ID
    const agentMap: Record<string, string> = {
      'kublai': 'kublai',
      'main': 'kublai',
      'mongke': 'mongke',
      'researcher': 'mongke',
      'ogedei': 'ogedei',
      'writer': 'ogedei',
      'temujin': 'temujin',
      'developer': 'temujin',
      'jochi': 'jochi',
      'analyst': 'jochi',
      'chagatai': 'chagatai',
      'ops': 'chagatai',
    };

    const agentId = agentMap[payload.source] || payload.agentId || payload.source;

    // Update based on event type
    switch (payload.eventType) {
      case 'status':
        if (payload.data.status) {
          webhookStore.updateStatus(agentId, payload.data.status);
        }
        break;

      case 'task':
        if (payload.data.task) {
          webhookStore.updateTask(agentId, payload.data.task);
        }
        break;

      case 'activity':
        if (payload.data.activity) {
          webhookStore.addActivity(agentId, {
            ...payload.data.activity,
            timestamp: payload.data.timestamp || new Date().toISOString(),
          });
        }
        break;

      case 'heartbeat':
        webhookStore.heartbeat(agentId);
        break;
    }

    // Get updated state
    const state = webhookStore.get(agentId);

    return NextResponse.json({
      success: true,
      agentId,
      state: {
        status: state?.status,
        lastUpdate: state?.lastUpdate,
        currentTask: state?.currentTask,
        activityCount: state?.activities?.length || 0,
      }
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: 'Invalid request' },
      { status: 400 }
    );
  }
}

// GET endpoint to retrieve all agent states
export async function GET() {
  const agents = webhookStore.getAll();

  return NextResponse.json({
    agents,
    count: agents.length,
  });
}
