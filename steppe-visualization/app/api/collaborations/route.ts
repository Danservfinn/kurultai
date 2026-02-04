import { NextResponse } from 'next/server';

// Mock collaboration data - in production this would query Neo4j LEARNED/COLLABORATES_WITH relationships
export async function GET() {
  const collaborations = [
    { from: 'researcher', to: 'writer', type: 'LEARNED', timestamp: new Date().toISOString() },
    { from: 'writer', to: 'main', type: 'LEARNED', timestamp: new Date().toISOString() },
    { from: 'developer', to: 'analyst', type: 'COLLABORATES_WITH', timestamp: new Date().toISOString() },
    { from: 'analyst', to: 'developer', type: 'COLLABORATES_WITH', timestamp: new Date().toISOString() },
    { from: 'main', to: 'researcher', type: 'CREATED', timestamp: new Date().toISOString() },
    { from: 'main', to: 'writer', type: 'CREATED', timestamp: new Date().toISOString() },
    { from: 'main', to: 'developer', type: 'CREATED', timestamp: new Date().toISOString() },
    { from: 'main', to: 'analyst', type: 'CREATED', timestamp: new Date().toISOString() },
    { from: 'main', to: 'ops', type: 'CREATED', timestamp: new Date().toISOString() },
    { from: 'researcher', to: 'main', type: 'LEARNED', timestamp: new Date().toISOString() },
    { from: 'developer', to: 'main', type: 'LEARNED', timestamp: new Date().toISOString() },
    { from: 'ops', to: 'main', type: 'COLLABORATES_WITH', timestamp: new Date().toISOString() },
  ];

  return NextResponse.json({ collaborations });
}
