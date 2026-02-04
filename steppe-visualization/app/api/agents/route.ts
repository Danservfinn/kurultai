import { NextResponse } from 'next/server';
import { webhookStore } from '../../lib/webhook-state';

// Gateway configuration
const GATEWAY_URL = process.env.GATEWAY_URL || 'http://localhost:18789';
const GATEWAY_TOKEN = process.env.GATEWAY_TOKEN || '';

// Agent definitions matching the mission-control plan
const AGENT_DEFINITIONS = [
  { id: 'main', name: 'Kublai', role: 'coordinator', sessionId: 'agent:main:main' },
  { id: 'researcher', name: 'Möngke', role: 'researcher', sessionId: 'agent:researcher:main' },
  { id: 'writer', name: 'Ögedei', role: 'writer', sessionId: 'agent:writer:main' },
  { id: 'developer', name: 'Temüjin', role: 'developer', sessionId: 'agent:developer:main' },
  { id: 'analyst', name: 'Jochi', role: 'analyst', sessionId: 'agent:analyst:main' },
  { id: 'ops', name: 'Chagatai', role: 'operations', sessionId: 'agent:ops:main' },
];

// Map internal IDs to visualization IDs
const ID_MAP: Record<string, string> = {
  'main': 'kublai',
  'researcher': 'mongke',
  'writer': 'ogedei',
  'developer': 'temujin',
  'analyst': 'jochi',
  'ops': 'chagatai',
};

export const dynamic = 'force-dynamic';
export const revalidate = 0;

async function fetchFromGateway(endpoint: string) {
  try {
    const headers: Record<string, string> = {
      'Accept': 'application/json',
    };

    if (GATEWAY_TOKEN) {
      headers['Authorization'] = `Bearer ${GATEWAY_TOKEN}`;
    }

    const response = await fetch(`${GATEWAY_URL}${endpoint}`, {
      headers,
      signal: AbortSignal.timeout(5000),
    });

    if (response.ok) {
      const data = await response.json();
      return { success: true, data };
    }

    return { success: false, error: `HTTP ${response.status}` };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
  }
}

export async function GET() {
  // Get webhook data first (highest priority for live data)
  const webhookAgents = webhookStore.getAll();
  const webhookAgentIds = new Set(webhookAgents.map(a => a.id));

  // Get alive agents from webhook (updated within last 5 minutes)
  const aliveWebhookIds = new Set(webhookStore.getAliveAgents());

  // Build response with webhook data
  const agents = AGENT_DEFINITIONS.map(def => {
    const vizId = ID_MAP[def.id] || def.id;
    const webhookData = webhookAgents.find(a => a.id === vizId);
    const isAlive = aliveWebhookIds.has(vizId);

    return {
      ...def,
      status: webhookData?.status || (isAlive ? 'working' : 'idle'),
      lastActive: webhookData?.lastUpdate || null,
      messageCount: 0,
      currentTask: webhookData?.currentTask,
      activityCount: webhookData?.activities?.length || 0,
      source: webhookData ? 'webhook' : 'fallback',
    };
  });

  // If we have webhook data, return it
  if (webhookAgents.length > 0) {
    return NextResponse.json({
      source: 'webhook',
      agents,
      webhookAgentCount: webhookAgents.length,
    });
  }

  // Try to fetch from gateway (second priority)
  const sessionsResult = await fetchFromGateway('/api/sessions');

  if (sessionsResult.success && sessionsResult.data) {
    const gatewayAgents = AGENT_DEFINITIONS.map(def => {
      const sessionData = (sessionsResult.data as any[]).find(
        (s: any) => s.sessionId === def.sessionId
      );

      return {
        ...def,
        status: sessionData ? 'working' : 'idle',
        lastActive: sessionData?.lastActivity || null,
        messageCount: sessionData?.messageCount || 0,
        source: 'gateway' as const,
      };
    });

    return NextResponse.json({
      source: 'gateway',
      agents: gatewayAgents
    });
  }

  // Fallback: Return agent definitions with simulated status
  return NextResponse.json({
    source: 'fallback',
    agents: AGENT_DEFINITIONS.map(def => ({
      ...def,
      status: 'idle',
      lastActive: null,
      messageCount: 0,
    })),
    gatewayError: sessionsResult.error,
  });
}
